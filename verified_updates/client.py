"""Persisted TUF verification, artifact validation and installation outcomes."""

from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from tuf.api import exceptions as tuf_errors
from tuf.api.metadata import Metadata, Root
from tuf.api.serialization import DeserializationError
from tuf.ngclient import Updater
from urllib3.exceptions import HTTPError as TransportError

from verified_updates.contracts import Release, UpdateError, UpdateResult, identifier
from verified_updates.installer import MAX_ARTIFACT_BYTES, activate, active_state
from verified_updates.storage import atomic_write, process_lock, read_json, write_json


def initialize_client(client: Path, bootstrap: Path, repository_url: str, app_id: str, platform: str) -> None:
    identifier(app_id)
    identifier(platform)
    url = urlsplit(repository_url)
    if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise UpdateError("INVALID_INPUT", "Repository must be an HTTP(S) URL without credentials, a query or a fragment.")
    if client.exists() and any(client.iterdir()):
        raise UpdateError("ALREADY_INITIALIZED", "Client directory must be empty for initialization.")
    bootstrap_bytes = bootstrap.read_bytes()
    try:
        root = Metadata.from_bytes(bootstrap_bytes)
        if not isinstance(root.signed, Root):
            raise UpdateError("INVALID_BOOTSTRAP", "Bootstrap metadata must have the TUF root role.")
        root.signed.verify_delegate("root", root.signed_bytes, root.signatures)
    except (DeserializationError, tuf_errors.RepositoryError) as exc:
        raise UpdateError("INVALID_BOOTSTRAP", f"Cannot validate bootstrap root: {exc}") from exc
    client.mkdir(parents=True, exist_ok=True)
    (client / "metadata").mkdir()
    atomic_write(client / "bootstrap-root.json", bootstrap_bytes)
    write_json(client / "client.json", {
        "schema_version": 1, "repository_url": repository_url.rstrip("/") + "/",
        "app_id": app_id, "platform": platform,
    })


def _failure(exc: Exception, stage: str) -> tuple[str, str]:
    if isinstance(exc, UpdateError):
        outcome = "failed" if exc.code in ("BUSY", "INSTALL_SELF_TEST_FAILED") else "rejected"
        return outcome, exc.code
    if isinstance(exc, (tuf_errors.LengthOrHashMismatchError, tuf_errors.DownloadLengthMismatchError)):
        return "rejected", "TARGET_INTEGRITY_FAILED" if stage == "download_artifact" else "METADATA_INTEGRITY_FAILED"
    if isinstance(exc, tuf_errors.UnsignedMetadataError):
        return "rejected", "SIGNATURE_THRESHOLD_NOT_MET"
    if isinstance(exc, tuf_errors.ExpiredMetadataError):
        return "rejected", "METADATA_EXPIRED"
    if isinstance(exc, (tuf_errors.BadVersionNumberError, tuf_errors.EqualVersionNumberError)):
        return "rejected", "METADATA_ROLLBACK"
    if isinstance(exc, (tuf_errors.DownloadError, TransportError)):
        return "failed", "DOWNLOAD_FAILED"
    if isinstance(exc, tuf_errors.RepositoryError):
        return "rejected", "METADATA_REJECTED"
    return "failed", "LOCAL_IO_FAILED"


def update(client: Path) -> UpdateResult:
    client = client.resolve()
    config = read_json(client / "client.json")
    state = active_state(client)
    before = Release.from_custom(state["release"]).sequence if state else None
    run_id = uuid4().hex
    result = UpdateResult(run_id, config["app_id"], "failed", "NOT_STARTED", "Update did not complete.", before, before)
    try:
        with process_lock(client / ".lock"):
            # Reload after locking: another updater may have completed meanwhile.
            state = active_state(client)
            before = Release.from_custom(state["release"]).sequence if state else None
            result.installed_before = result.installed_after = before
            repository = config["repository_url"]
            result.stage = "refresh_metadata"
            updater = Updater(
                str(client / "metadata"), repository + "metadata/",
                target_dir=str(client / "downloads"), target_base_url=repository + "targets/",
                bootstrap=None if (client / "metadata" / "root.json").exists() else (client / "bootstrap-root.json").read_bytes(),
            )
            updater.refresh()
            result.stage = "select_release"
            target_path = f"apps/{config['app_id']}/{config['platform']}/application.zip"
            target = updater.get_targetinfo(target_path)
            if target is None:
                raise UpdateError("NO_RELEASE", "No authorized release exists for this application and platform.")
            release = Release.from_custom(target.custom)
            if release.app_id != config["app_id"] or release.platform != config["platform"]:
                raise UpdateError("WRONG_APPLICATION", "Signed target identity differs from the requested application or platform.")
            result.version = release.version
            if target.length > MAX_ARTIFACT_BYTES:
                raise UpdateError("PACKAGE_TOO_LARGE", "Signed artifact exceeds this client's download limit.")
            digest = target.hashes.get("sha256")
            if digest is None:
                raise UpdateError("INVALID_RELEASE_METADATA", "The application policy requires a SHA-256 artifact digest.")
            ordering_path = client / "ordering.json"
            ordering = read_json(ordering_path) if ordering_path.exists() else {"sequence": 0, "sha256": None}
            if release.sequence < ordering["sequence"]:
                raise UpdateError("RELEASE_ROLLBACK", "Signed application sequence is below the highest accepted release.")
            if release.sequence == ordering["sequence"] and digest != ordering["sha256"]:
                raise UpdateError("RELEASE_SEQUENCE_REUSED", "The same application sequence was reused for a different artifact.")
            if state and before == release.sequence and state["sha256"] == digest:
                result.outcome, result.reason_code, result.detail = "up_to_date", "CURRENT_RELEASE", "Installed release matches the verified target."
            else:
                result.stage = "download_artifact"
                artifact = Path(updater.download_target(target, str(client / "downloads" / f"{run_id}.zip")))
                # Security state can advance even if an authorized release later fails its self-test.
                write_json(ordering_path, {"schema_version": 1, "sequence": release.sequence, "sha256": digest})
                result.stage = "install"
                activate(client, artifact, release, digest)
                result.outcome, result.reason_code = "updated", "VERIFIED_AND_INSTALLED"
                result.detail = "TUF metadata and artifact verified; application self-test passed; active pointer committed."
                result.installed_after = release.sequence
            result.stage = "complete"
    except (UpdateError, tuf_errors.RepositoryError, tuf_errors.DownloadError, TransportError, OSError) as exc:
        result.outcome, result.reason_code = _failure(exc, result.stage)
        result.detail = f"{type(exc).__name__}: {exc}"
    write_json(client / "events" / f"{run_id}.json", result.to_dict())
    return result


"""TUF publication with private authoritative state and separate approvals."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import shutil
from typing import Any

from tuf.api.metadata import Metadata, MetaFile, Root, Snapshot, TargetFile, Targets, Timestamp

from verified_updates.contracts import Release, UpdateError, identifier
from verified_updates.keys import generate_signer, load_signer
from verified_updates.installer import MAX_ARTIFACT_BYTES
from verified_updates.storage import atomic_write, process_lock, read_json, write_json


ROLES = ("root", "targets", "snapshot", "timestamp")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def configuration(publisher: Path) -> dict[str, Any]:
    return read_json(publisher / "publisher.json")


def authoritative(publisher: Path, role: str) -> Metadata:
    return Metadata.from_file(str(publisher / "state" / f"{role}.json"))


def _sign(publisher: Path, metadata: Metadata, role: str, passphrase: bytes, count: int | None = None) -> None:
    metadata.signatures.clear()
    keyids = configuration(publisher)["keys"][role]
    for keyid in keyids[:count]:
        metadata.sign(load_signer(publisher / "keys", keyid, passphrase), append=True)


def _store_publication(publisher: Path, targets: Metadata, snapshot: Metadata, timestamp: Metadata) -> None:
    repository = Path(configuration(publisher)["repository"])
    # Publish immutable versioned metadata before the mutable timestamp pointer.
    for role, metadata in (("targets", targets), ("snapshot", snapshot)):
        atomic_write(repository / "metadata" / f"{metadata.signed.version}.{role}.json", metadata.to_bytes())
    atomic_write(repository / "metadata" / "timestamp.json", timestamp.to_bytes())
    for role, metadata in (("targets", targets), ("snapshot", snapshot), ("timestamp", timestamp)):
        atomic_write(publisher / "state" / f"{role}.json", metadata.to_bytes())


def _refresh_publication(publisher: Path, targets: Metadata, passphrase: bytes) -> None:
    root = authoritative(publisher, "root")
    root.signed.verify_delegate("targets", targets.signed_bytes, targets.signatures)
    snapshot = Metadata(Snapshot(
        version=authoritative(publisher, "snapshot").signed.version + 1,
        expires=utc_now() + timedelta(days=7),
        meta={"targets.json": MetaFile.from_data(targets.signed.version, targets.to_bytes(), ["sha256"])},
    ))
    _sign(publisher, snapshot, "snapshot", passphrase)
    timestamp = Metadata(Timestamp(
        version=authoritative(publisher, "timestamp").signed.version + 1,
        expires=utc_now() + timedelta(days=1),
        snapshot_meta=MetaFile.from_data(snapshot.signed.version, snapshot.to_bytes(), ["sha256"]),
    ))
    _sign(publisher, timestamp, "timestamp", passphrase)
    _store_publication(publisher, targets, snapshot, timestamp)


def initialize(publisher: Path, repository: Path, passphrase: bytes) -> Path:
    publisher, repository = publisher.resolve(), repository.resolve()
    if publisher.is_relative_to(repository) or repository.is_relative_to(publisher):
        raise UpdateError("UNSAFE_LAYOUT", "Publisher and public repository must be separate directory trees.")
    if publisher.exists() and any(publisher.iterdir()):
        raise UpdateError("ALREADY_INITIALIZED", "Publisher directory must be empty for initialization.")
    if repository.exists() and any(repository.iterdir()):
        raise UpdateError("ALREADY_INITIALIZED", "Repository directory must be empty for initialization.")
    publisher.mkdir(parents=True, exist_ok=True)
    repository.mkdir(parents=True, exist_ok=True)
    with process_lock(publisher / ".lock"):
        root = Metadata(Root(version=1, expires=utc_now() + timedelta(days=365), consistent_snapshot=True))
        signers = {}
        for role in ROLES:
            signers[role] = [generate_signer(publisher / "keys", passphrase) for _ in range(3 if role in ("root", "targets") else 1)]
            for signer in signers[role]:
                root.signed.add_key(signer.public_key, role)
            root.signed.roles[role].threshold = 2 if role in ("root", "targets") else 1
        write_json(publisher / "publisher.json", {
            "schema_version": 1,
            "repository": str(repository),
            "keys": {role: [s.public_key.keyid for s in signers[role]] for role in ROLES},
        })
        for signer in signers["root"][:2]:
            root.sign(signer, append=True)
        root.signed.verify_delegate("root", root.signed_bytes, root.signatures)
        atomic_write(publisher / "state" / "root.json", root.to_bytes())
        bootstrap = publisher / "bootstrap" / "root.json"
        atomic_write(bootstrap, root.to_bytes())
        atomic_write(repository / "metadata" / "1.root.json", root.to_bytes())
        targets = Metadata(Targets(version=1, expires=utc_now() + timedelta(days=30)))
        _sign(publisher, targets, "targets", passphrase, 2)
        snapshot = Metadata(Snapshot(version=1, expires=utc_now() + timedelta(days=7), meta={
            "targets.json": MetaFile.from_data(1, targets.to_bytes(), ["sha256"]),
        }))
        _sign(publisher, snapshot, "snapshot", passphrase)
        timestamp = Metadata(Timestamp(version=1, expires=utc_now() + timedelta(days=1),
            snapshot_meta=MetaFile.from_data(1, snapshot.to_bytes(), ["sha256"])))
        _sign(publisher, timestamp, "timestamp", passphrase)
        _store_publication(publisher, targets, snapshot, timestamp)
        return bootstrap


def prepare_release(publisher: Path, artifact: Path, release: Release) -> str:
    """Prepare unsigned targets metadata from PRIVATE state, never server data."""
    with process_lock(publisher / ".lock"):
        if artifact.stat().st_size > MAX_ARTIFACT_BYTES:
            raise UpdateError("PACKAGE_TOO_LARGE", "Artifact exceeds the updater's download limit.")
        targets = authoritative(publisher, "targets")
        existing = targets.signed.targets.get(release.target_path)
        if existing and release.sequence <= Release.from_custom(existing.custom).sequence:
            raise UpdateError("RELEASE_ROLLBACK", "New release sequence must exceed the previously published sequence.")
        pending_id = secrets.token_hex(12)
        pending = publisher / "pending" / pending_id
        pending.mkdir(parents=True)
        shutil.copyfile(artifact, pending / "artifact.zip")
        target = TargetFile.from_file(release.target_path, str(pending / "artifact.zip"), ["sha256"])
        target.unrecognized_fields["custom"] = release.to_custom()
        base_version = targets.signed.version
        targets.signed.version += 1
        targets.signed.expires = utc_now() + timedelta(days=30)
        targets.signed.targets[release.target_path] = target
        targets.signatures.clear()
        atomic_write(pending / "targets.json", targets.to_bytes())
        write_json(pending / "release.json", {
            "schema_version": 1, "base_version": base_version,
            "target_path": release.target_path, "published": False,
        })
        return pending_id


def _pending(publisher: Path, pending_id: str) -> Path:
    identifier(pending_id)
    return publisher / "pending" / pending_id


def _review_pending(publisher: Path, pending: Path):
    manifest = read_json(pending / "release.json")
    if manifest["published"]:
        raise UpdateError("ALREADY_PUBLISHED", "This release was already published.")
    if authoritative(publisher, "targets").signed.version != manifest["base_version"]:
        raise UpdateError("STALE_APPROVAL", "Repository changed. Prepare and approve a new release.")
    metadata = Metadata.from_file(str(pending / "targets.json"))
    now = utc_now()
    if metadata.signed.is_expired(now) or authoritative(publisher, "root").signed.is_expired(now):
        raise UpdateError("METADATA_EXPIRED", "Renew the expired metadata before publishing this release.")
    target = metadata.signed.targets[manifest["target_path"]]
    if target.length > MAX_ARTIFACT_BYTES:
        raise UpdateError("PACKAGE_TOO_LARGE", "Artifact exceeds the updater's download limit.")
    artifact = (pending / "artifact.zip").read_bytes()
    target.verify_length_and_hashes(artifact)
    return manifest, metadata, target, artifact


def inspect_release(publisher: Path, pending_id: str) -> dict:
    with process_lock(publisher / ".lock"):
        _, metadata, target, _ = _review_pending(publisher, _pending(publisher, pending_id))
        root = authoritative(publisher, "root").signed
        role = root.roles["targets"]
        verified_signers = []
        for keyid in role.keyids:
            signature = metadata.signatures.get(keyid)
            if signature is not None:
                root.keys[keyid].verify_signature(signature, metadata.signed_bytes)
                verified_signers.append(keyid)
        return {
            "release": Release.from_custom(target.custom).to_custom()["verified_updates"],
            "sha256": target.hashes["sha256"], "bytes": target.length,
            "verified_signatures": len(verified_signers), "required_signatures": role.threshold,
            "signers": verified_signers,
        }


def approve_release(publisher: Path, pending_id: str, signer_number: int, passphrase: bytes) -> int:
    with process_lock(publisher / ".lock"):
        if signer_number not in (1, 2, 3):
            raise UpdateError("INVALID_INPUT", "Release signer number must be 1, 2, or 3.")
        pending = _pending(publisher, pending_id)
        _, metadata, _, _ = _review_pending(publisher, pending)
        keyid = configuration(publisher)["keys"]["targets"][signer_number - 1]
        metadata.sign(load_signer(publisher / "keys", keyid, passphrase), append=True)
        atomic_write(pending / "targets.json", metadata.to_bytes())
        return len(metadata.signatures)


def publish_release(publisher: Path, pending_id: str, passphrase: bytes) -> str:
    with process_lock(publisher / ".lock"):
        pending = _pending(publisher, pending_id)
        manifest, metadata, target, artifact = _review_pending(publisher, pending)
        # Raises the real TUF UnsignedMetadataError if approvals are insufficient.
        authoritative(publisher, "root").signed.verify_delegate("targets", metadata.signed_bytes, metadata.signatures)
        repository = Path(configuration(publisher)["repository"])
        target_path = Path(target.path)
        public_artifact = repository / "targets" / target_path.parent / f"{target.hashes['sha256']}.{target_path.name}"
        atomic_write(public_artifact, artifact)
        _refresh_publication(publisher, metadata, passphrase)
        manifest["published"] = True
        write_json(pending / "release.json", manifest)
        return target.path


def rotate_targets_key(publisher: Path, signer_number: int, passphrase: bytes) -> str:
    """Authorize a new release key with a new root and republish targets."""
    with process_lock(publisher / ".lock"):
        if signer_number not in (1, 2, 3):
            raise UpdateError("INVALID_INPUT", "Release signer number must be 1, 2, or 3.")
        config = configuration(publisher)
        old_root = authoritative(publisher, "root")
        root = Metadata.from_bytes(old_root.to_bytes())
        new_signer = generate_signer(publisher / "keys", passphrase)
        old_keyid = config["keys"]["targets"][signer_number - 1]
        root.signed.revoke_key(old_keyid, "targets")
        root.signed.add_key(new_signer.public_key, "targets")
        root.signed.version += 1
        root.signed.expires = utc_now() + timedelta(days=365)
        _sign(publisher, root, "root", passphrase, 2)
        old_root.signed.verify_delegate("root", root.signed_bytes, root.signatures)
        root.signed.verify_delegate("root", root.signed_bytes, root.signatures)
        config["keys"]["targets"][signer_number - 1] = new_signer.public_key.keyid
        # Root signers are unchanged: their quorum authorizes the targets-key change.
        write_json(publisher / "publisher.json", config)
        atomic_write(publisher / "state" / "root.json", root.to_bytes())
        repository = Path(config["repository"])
        atomic_write(repository / "metadata" / f"{root.signed.version}.root.json", root.to_bytes())
        targets = authoritative(publisher, "targets")
        targets.signed.version += 1
        targets.signed.expires = utc_now() + timedelta(days=30)
        _sign(publisher, targets, "targets", passphrase, 2)
        _refresh_publication(publisher, targets, passphrase)
        return new_signer.public_key.keyid


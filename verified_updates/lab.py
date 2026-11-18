"""Real HTTP experiments. Forged quorum fixtures are explicitly privileged setup."""

from datetime import timedelta
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from uuid import uuid4

from tuf.api.exceptions import UnsignedMetadataError
from tuf.api.metadata import Metadata, MetaFile, Snapshot, Timestamp

from verified_updates.client import initialize_client
from verified_updates.baselines import run_comparison
from verified_updates.contracts import UpdateError
from verified_updates.publisher import (
    _sign, approve_release, authoritative, configuration, initialize, inspect_release,
    prepare_release, publish_release, rotate_targets_key, utc_now,
)
from verified_updates.reference import reference_bundle
from verified_updates.report import render_report
from verified_updates.server import serve_directory
from verified_updates.storage import atomic_write, read_json, write_json


def public_snapshot(repository: Path) -> dict[str, bytes]:
    return {str(path.relative_to(repository)): path.read_bytes() for path in (repository / "metadata").glob("*.json")}


def restore_publication(repository: Path, snapshot: dict[str, bytes]) -> None:
    # Immutable extra versions can remain. Restore the captured timestamp last.
    for name, content in sorted(snapshot.items(), key=lambda item: item[0].endswith("timestamp.json")):
        atomic_write(repository / name, content)


def public_artifact(publisher: Path) -> Path:
    targets = authoritative(publisher, "targets")
    target = next(iter(targets.signed.targets.values()))
    path = Path(target.path)
    return Path(configuration(publisher)["repository"]) / "targets" / path.parent / f"{target.hashes['sha256']}.{path.name}"


def force_insufficient_quorum(publisher: Path, pending_id: str, passphrase: bytes) -> None:
    """Publish one-signature targets with VALID snapshot/timestamp support.

    This uses fixture access to snapshot/timestamp keys to reach the intended
    targets-signature check. It is not claimed to model server-only authority.
    Publisher authoritative state is intentionally untouched.
    """
    pending = publisher / "pending" / pending_id
    targets = Metadata.from_file(str(pending / "targets.json"))
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
    repository = Path(configuration(publisher)["repository"])
    atomic_write(repository / "metadata" / f"{targets.signed.version}.targets.json", targets.to_bytes())
    atomic_write(repository / "metadata" / f"{snapshot.signed.version}.snapshot.json", snapshot.to_bytes())
    atomic_write(repository / "metadata" / "timestamp.json", timestamp.to_bytes())


def _client_environment() -> dict[str, str]:
    # Lab repositories are loopback-only. Preserve other proxy policy while
    # keeping local traffic off corporate or execution-environment proxies.
    environment = os.environ.copy()
    previous = next((value for key, value in environment.items() if key.lower() == "no_proxy"), "")
    for key in list(environment):
        if key.lower() == "no_proxy":
            del environment[key]
    environment["NO_PROXY"] = ",".join(filter(None, (previous, "127.0.0.1", "localhost")))
    return environment


def invoke_update(client: Path) -> dict:
    process = subprocess.run(
        [sys.executable, "-m", "verified_updates", "client", "update", "--client", str(client)],
        cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True, timeout=45,
        env=_client_environment(),
    )
    if process.returncode not in (0, 3, 4):
        raise RuntimeError(f"Update subprocess failed: {process.stdout}\n{process.stderr}")
    result = json.loads(process.stdout)
    result["process_exit_code"] = process.returncode
    return result


def interrupt_before_activation(client: Path) -> int:
    """Kill a real updater process at the commit boundary, after its self-test.

    This injected fault lives in a lab subprocess. The production client has
    no fault-injection or verification-bypass option.
    """
    script = '''
import os, sys
from pathlib import Path
import verified_updates.installer as installer
from verified_updates.client import update
original = installer.write_json
def interrupted_write(path, value):
    if path.name == "active.json":
        os._exit(73)
    original(path, value)
installer.write_json = interrupted_write
update(Path(sys.argv[1]))
raise SystemExit("Fault point was never reached")
'''
    process = subprocess.run([sys.executable, "-c", script, str(client)],
        cwd=Path(__file__).resolve().parent.parent, env=_client_environment(),
        capture_output=True, text=True, timeout=45)
    if process.returncode != 73:
        raise RuntimeError(f"Interruption scenario missed the commit boundary: {process.stdout} {process.stderr}")
    return process.returncode


def run_demo(directory: Path | None = None) -> dict:
    base = (directory or Path(".runtime") / f"demo-{uuid4().hex[:12]}").resolve()
    if base.exists():
        raise UpdateError("DIRECTORY_EXISTS", "Demo directory must be new; existing evidence is never overwritten.")
    base.mkdir(parents=True)
    publisher, repository = base / "publisher", base / "repository"
    passphrase = secrets.token_urlsafe(32).encode()
    bootstrap = initialize(publisher, repository, passphrase)
    # Demo keys are encrypted with an unrecorded random passphrase. These are
    # disposable identities, not the keys for a persistent real repository.
    cases = []

    def publish(sequence, version, broken=False):
        artifact, release = reference_bundle(base / "builds", sequence, version, broken=broken)
        pending = prepare_release(publisher, artifact, release)
        approve_release(publisher, pending, 1, passphrase)
        approve_release(publisher, pending, 2, passphrase)
        review = inspect_release(publisher, pending)
        publish_release(publisher, pending, passphrase)
        return review

    def record(name, client, outcome, reason, before, after):
        result = invoke_update(client)
        passed = (result["outcome"], result["reason_code"], result["installed_before"], result["installed_after"]) == (outcome, reason, before, after)
        cases.append({"scenario": name, "passed": passed, "expected": {"outcome": outcome, "reason_code": reason, "before": before, "after": after}, "actual": result})

    with serve_directory(repository) as url:
        first_review = publish(1, "1.0.0")
        old_publication = public_snapshot(repository)
        old_timestamp = (repository / "metadata" / "timestamp.json").read_bytes()
        main_client = base / "clients" / "main"
        initialize_client(main_client, bootstrap, url, "csv-inspector", "windows-amd64")
        record("genuine_release_v1", main_client, "updated", "VERIFIED_AND_INSTALLED", None, 1)
        cases[-1]["publisher_review"] = first_review
        publish(2, "1.1.0")
        good = public_snapshot(repository)
        artifact = public_artifact(publisher)
        original = artifact.read_bytes()
        tampered = bytearray(original)
        changed_offset = len(original) // 2
        tampered[changed_offset] ^= 1
        atomic_write(artifact, bytes(tampered))
        record("artifact_substitution", main_client, "rejected", "TARGET_INTEGRITY_FAILED", 1, 1)
        # The fixture changed one byte, so restore it in place between clients.
        # Windows can deny an atomic rename while the prior HTTP reader closes.
        with artifact.open("r+b") as stream:
            stream.seek(changed_offset)
            stream.write(original[changed_offset:changed_offset + 1])
        record("genuine_release_v2_after_rejection", main_client, "updated", "VERIFIED_AND_INSTALLED", 1, 2)
        atomic_write(repository / "metadata" / "timestamp.json", old_timestamp)
        record("metadata_rollback_after_process_restart", main_client, "rejected", "METADATA_ROLLBACK", 2, 2)
        restore_publication(repository, good)

        def seeded_client(name):
            client = base / "clients" / name
            initialize_client(client, bootstrap, url, "csv-inspector", "windows-amd64")
            seed = invoke_update(client)
            if seed["outcome"] != "updated":
                raise RuntimeError(f"Could not seed independent scenario client: {seed}")
            return client

        expiry_client = seeded_client("expiry")
        timestamp = authoritative(publisher, "timestamp")
        timestamp.signed.version += 1
        timestamp.signed.expires = utc_now() - timedelta(hours=1)
        _sign(publisher, timestamp, "timestamp", passphrase)
        atomic_write(repository / "metadata" / "timestamp.json", timestamp.to_bytes())
        record("correctly_signed_expired_metadata", expiry_client, "rejected", "METADATA_EXPIRED", 2, 2)
        restore_publication(repository, good)

        quorum_client = seeded_client("quorum")
        artifact3, release3 = reference_bundle(base / "builds", 3, "1.2.0")
        pending = prepare_release(publisher, artifact3, release3)
        approve_release(publisher, pending, 1, passphrase)
        quorum_review = inspect_release(publisher, pending)
        try:
            publish_release(publisher, pending, passphrase)
        except UnsignedMetadataError as exc:
            publisher_rejection = f"{type(exc).__name__}: {exc}"
        else:
            raise RuntimeError("Publisher incorrectly accepted one release signature.")
        force_insufficient_quorum(publisher, pending, passphrase)
        record("insufficient_targets_signatures", quorum_client, "rejected", "SIGNATURE_THRESHOLD_NOT_MET", 2, 2)
        cases[-1]["publisher_rejection"] = publisher_rejection
        cases[-1]["publisher_review"] = quorum_review
        restore_publication(repository, good)

        # Seed this client on v1 so the v2 snapshot is genuinely new to it.
        # A client with a valid cached v2 snapshot correctly need not refetch it.
        restore_publication(repository, old_publication)
        mixed_client = seeded_client("mixed")
        restore_publication(repository, good)
        snapshot_version = authoritative(publisher, "snapshot").signed.version
        previous_snapshot = old_publication[str(Path("metadata") / f"{snapshot_version - 1}.snapshot.json")]
        atomic_write(repository / "metadata" / f"{snapshot_version}.snapshot.json", previous_snapshot)
        record("inconsistent_snapshot", mixed_client, "rejected", "METADATA_INTEGRITY_FAILED", 1, 1)
        restore_publication(repository, good)

        rotate_targets_key(publisher, 1, passphrase)
        publish(3, "1.2.0")
        record("authorized_release_key_rotation", main_client, "updated", "VERIFIED_AND_INSTALLED", 2, 3)
        publish(4, "1.3.0")
        before_interruption = read_json(main_client / "active.json")
        exit_code = interrupt_before_activation(main_client)
        after_interruption = read_json(main_client / "active.json")
        cases.append({"scenario": "interrupted_activation", "passed": before_interruption == after_interruption,
            "actual": {"process_exit_code": exit_code, "active_state_unchanged": before_interruption == after_interruption,
                       "installed_before": 3, "installed_after": after_interruption["release"]["verified_updates"]["sequence"]}})
        record("recovery_after_interruption", main_client, "updated", "VERIFIED_AND_INSTALLED", 3, 4)
        publish(5, "1.4.0", broken=True)
        record("application_self_test_failure", main_client, "failed", "INSTALL_SELF_TEST_FAILED", 4, 4)

        comparison = run_comparison(repository, url, (base / "builds" / "csv-inspector-1.zip").read_bytes(), original, cases)

        app = subprocess.run(
            [sys.executable, "-m", "verified_updates", "client", "run", "--client", str(main_client), "--", str((Path(__file__).parent.parent / "demo_app" / "sample.csv").resolve())],
            cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True, timeout=15,
        )
        if app.returncode != 0:
            raise RuntimeError(f"Previously installed application failed to run: {app.stdout} {app.stderr}")
        application_output = json.loads(app.stdout)
        if application_output.get("version") != "1.3.0" or "numeric_summaries" not in application_output:
            raise RuntimeError("Installed application did not retain the expected working release.")

    report = {
        "schema_version": 1, "directory": str(base),
        "all_passed": all(case["passed"] for case in cases) and all(row["passed"] for row in comparison),
        "cases": cases, "comparison": comparison,
        "installed_application_output": application_output,
        "notes": [
            "Every update ran in a new client process over a real loopback HTTP server.",
            "Signing identities are simulated on one machine; keys are outside the served repository.",
            "Quorum and expired-metadata scenarios use privileged fixture setup to reach the intended check.",
            "This milestone installs Python source bundles; a portable executable and desktop interface are pending.",
            "Ephemeral demo signing passphrase was not persisted; generate a new demo for another run.",
            "Comparison clients evaluate artifact acceptance only; they do not install applications.",
        ],
    }
    write_json(base / "report.json", report)
    render_report(report, base / "report.html")
    return report


from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import socket
import zipfile

import pytest
from tuf.api.exceptions import UnsignedMetadataError
from tuf.api.metadata import Metadata

from verified_updates.client import initialize_client, update
from verified_updates.contracts import Release, UpdateError
from verified_updates.installer import active_state
from verified_updates.keys import load_signer
from verified_updates.lab import force_insufficient_quorum, interrupt_before_activation, invoke_update, public_artifact
from verified_updates.publisher import (
    _sign, approve_release, authoritative, configuration, inspect_release, prepare_release,
    publish_release, rotate_targets_key, utc_now,
)
from verified_updates.reference import reference_bundle
from verified_updates.storage import atomic_write, read_json, write_json


def test_real_updates_and_reference_application(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    lab.publish(2)
    result = invoke_update(client)
    assert result["outcome"] == "updated", result
    assert result["installed_before"] == 1
    assert result["installed_after"] == 2
    sample = Path(__file__).resolve().parents[1] / "demo_app" / "sample.csv"
    process = subprocess.run(
        [sys.executable, "-m", "verified_updates", "client", "run", "--client", str(client), "--", str(sample)],
        capture_output=True, text=True, check=True,
    )
    output = json.loads(process.stdout)
    assert output["version"] == "1.1.0"
    assert output["row_count"] == 4
    assert output["numeric_summaries"]["score"]["mean"] == 89.5
    assert update(client).outcome == "up_to_date"
    assert not list(lab.repository.rglob("*.pem"))
    assert all(b"ENCRYPTED PRIVATE KEY" in key.read_bytes() for key in (lab.publisher / "keys").glob("*.pem"))


def test_modified_artifact_rejected_and_retry_recovers(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    previous = active_state(client)
    lab.publish(2)
    artifact = public_artifact(lab.publisher)
    genuine = artifact.read_bytes()
    altered = bytearray(genuine)
    altered[len(altered) // 2] ^= 1
    atomic_write(artifact, bytes(altered))
    result = update(client)
    assert result.outcome == "rejected", result.to_dict()
    assert result.reason_code == "TARGET_INTEGRITY_FAILED"
    assert result.stage == "download_artifact"
    assert active_state(client) == previous
    atomic_write(artifact, genuine)
    assert update(client).installed_after == 2


def test_rollback_protection_survives_new_process(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    old_timestamp = (lab.repository / "metadata" / "timestamp.json").read_bytes()
    lab.publish(2)
    assert invoke_update(client)["installed_after"] == 2
    atomic_write(lab.repository / "metadata" / "timestamp.json", old_timestamp)
    result = invoke_update(client)
    assert result["reason_code"] == "METADATA_ROLLBACK", result
    assert result["installed_after"] == 2


def test_two_distinct_signers_required(repository_lab):
    lab = repository_lab
    artifact, release = reference_bundle(lab.base / "builds", 1, "1.0.0")
    pending = prepare_release(lab.publisher, artifact, release)
    assert approve_release(lab.publisher, pending, 1, lab.passphrase) == 1
    assert approve_release(lab.publisher, pending, 1, lab.passphrase) == 1
    review = inspect_release(lab.publisher, pending)
    assert (review["verified_signatures"], review["required_signatures"]) == (1, 2)
    assert review["release"]["sequence"] == 1
    with pytest.raises(UnsignedMetadataError, match="1/2"):
        publish_release(lab.publisher, pending, lab.passphrase)
    assert approve_release(lab.publisher, pending, 2, lab.passphrase) == 2
    publish_release(lab.publisher, pending, lab.passphrase)
    assert update(lab.client()).outcome == "updated"


def test_bad_bootstrap_leaves_client_directory_available(repository_lab):
    lab = repository_lab
    bootstrap = lab.base / "bad-root.json"
    root = Metadata.from_file(str(lab.bootstrap))
    root.signatures.pop(next(iter(root.signatures)))
    bootstrap.write_bytes(root.to_bytes())
    with pytest.raises(UpdateError, match="bootstrap root"):
        initialize_client(lab.base / "client", bootstrap, lab.url, "csv-inspector", "windows-amd64")
    assert not (lab.base / "client").exists()
    lab.client()


def test_changed_pending_bundle_cannot_be_inspected_or_approved(repository_lab):
    from tuf.api.exceptions import LengthOrHashMismatchError

    lab = repository_lab
    artifact, release = reference_bundle(lab.base / "builds", 1, "1.0.0")
    pending = prepare_release(lab.publisher, artifact, release)
    (lab.publisher / "pending" / pending / "artifact.zip").write_bytes(b"wrong file")
    with pytest.raises(LengthOrHashMismatchError):
        inspect_release(lab.publisher, pending)
    with pytest.raises(LengthOrHashMismatchError):
        approve_release(lab.publisher, pending, 1, lab.passphrase)


def test_client_checks_quorum_with_valid_surrounding_metadata(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    artifact, release = reference_bundle(lab.base / "builds", 2, "1.1.0")
    pending = prepare_release(lab.publisher, artifact, release)
    approve_release(lab.publisher, pending, 1, lab.passphrase)
    force_insufficient_quorum(lab.publisher, pending, lab.passphrase)
    result = update(client)
    assert result.reason_code == "SIGNATURE_THRESHOLD_NOT_MET", result.to_dict()
    assert "targets was signed by 1/2 keys" in result.detail
    assert result.installed_after == 1


def test_correctly_signed_expired_timestamp_is_rejected(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    timestamp = authoritative(lab.publisher, "timestamp")
    timestamp.signed.version += 1
    timestamp.signed.expires = utc_now() - timedelta(minutes=1)
    _sign(lab.publisher, timestamp, "timestamp", lab.passphrase)
    atomic_write(lab.repository / "metadata" / "timestamp.json", timestamp.to_bytes())
    result = update(client)
    assert result.reason_code == "METADATA_EXPIRED", result.to_dict()
    assert result.installed_after == 1


def test_new_inconsistent_snapshot_is_rejected(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    lab.publish(2)
    version = authoritative(lab.publisher, "snapshot").signed.version
    atomic_write(lab.repository / "metadata" / f"{version}.snapshot.json", b"changed snapshot")
    result = update(client)
    assert result.reason_code == "METADATA_INTEGRITY_FAILED", result.to_dict()
    assert result.installed_after == 1


def test_authorized_targets_key_rotation(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    old_root = authoritative(lab.publisher, "root")
    old_keyid = configuration(lab.publisher)["keys"]["targets"][0]
    new_keyid = rotate_targets_key(lab.publisher, 1, lab.passphrase)
    new_root = authoritative(lab.publisher, "root")
    assert new_root.signed.version == 2
    assert old_keyid not in new_root.signed.roles["targets"].keyids
    assert new_keyid in new_root.signed.roles["targets"].keyids
    old_root.signed.verify_delegate("root", new_root.signed_bytes, new_root.signatures)
    new_root.signed.verify_delegate("root", new_root.signed_bytes, new_root.signatures)
    lab.publish(2)
    result = invoke_update(client)
    assert result["installed_after"] == 2, result
    assert Metadata.from_file(str(client / "metadata" / "root.json")).signed.version == 2


def test_failed_application_keeps_previous_active_version(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    previous = active_state(client)
    lab.publish(2, broken=True)
    result = update(client)
    assert result.reason_code == "INSTALL_SELF_TEST_FAILED", result.to_dict()
    assert result.installed_after == 1
    assert active_state(client) == previous
    assert read_json(client / "ordering.json")["sequence"] == 2
    assert invoke_update(client)["reason_code"] == "INSTALL_SELF_TEST_FAILED"


def test_real_process_crash_before_activation_recovers(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    previous = active_state(client)
    lab.publish(2)
    assert interrupt_before_activation(client) == 73
    assert active_state(client) == previous
    assert read_json(client / "ordering.json")["sequence"] == 2
    recovered = invoke_update(client)
    assert recovered["outcome"] == "updated", recovered
    assert recovered["installed_before"] == 1
    assert recovered["installed_after"] == 2


@pytest.mark.parametrize("bad_name", ["../escape.txt", "/escape.txt", "C:/escape.txt", "CON.txt", "APP.py", "folder\\escape.txt", "zero\x00name.txt"])
def test_signed_unsafe_archive_rejected_before_execution(repository_lab, bad_name):
    lab = repository_lab
    artifact, release = reference_bundle(lab.base / "builds", 1, "1.0.0")
    with zipfile.ZipFile(artifact, "a") as archive:
        # Override after construction so Windows' writer does not normalize
        # hostile names before the installer gets a chance to inspect them.
        entry = zipfile.ZipInfo("placeholder")
        entry.filename = bad_name
        archive.writestr(entry, "unsafe entry")
    pending = prepare_release(lab.publisher, artifact, release)
    for signer in (1, 2):
        approve_release(lab.publisher, pending, signer, lab.passphrase)
    publish_release(lab.publisher, pending, lab.passphrase)
    client = lab.client()
    result = update(client)
    assert result.reason_code == "INVALID_PACKAGE", result.to_dict()
    assert not (client / "active.json").exists()
    assert not (lab.base / "escape.txt").exists()


def test_publisher_uses_private_state_instead_of_compromised_repository(repository_lab):
    lab = repository_lab
    lab.publish(1)
    version = authoritative(lab.publisher, "targets").signed.version
    atomic_write(lab.repository / "metadata" / f"{version}.targets.json", b"attacker-controlled public metadata")
    lab.publish(2)
    result = update(lab.client())
    assert result.installed_after == 2, result.to_dict()


def test_wrong_application_identity_is_rejected(repository_lab):
    lab = repository_lab
    artifact, release = reference_bundle(lab.base / "builds", 1, "1.0.0")
    pending = prepare_release(lab.publisher, artifact, release)
    metadata_path = lab.publisher / "pending" / pending / "targets.json"
    metadata = Metadata.from_file(str(metadata_path))
    metadata.signed.targets[release.target_path].unrecognized_fields["custom"]["verified_updates"]["app_id"] = "other-app"
    atomic_write(metadata_path, metadata.to_bytes())
    for signer in (1, 2):
        approve_release(lab.publisher, pending, signer, lab.passphrase)
    publish_release(lab.publisher, pending, lab.passphrase)
    result = update(lab.client())
    assert result.reason_code == "WRONG_APPLICATION", result.to_dict()
    assert result.installed_after is None


def test_wrong_passphrase_cannot_unlock_publisher_key(repository_lab):
    lab = repository_lab
    keyid = configuration(lab.publisher)["keys"]["targets"][0]
    with pytest.raises(UpdateError, match="decrypt"):
        load_signer(lab.publisher / "keys", keyid, b"incorrect-password")


def test_pending_approvals_cannot_overwrite_a_newer_publication(repository_lab):
    lab = repository_lab
    artifact, release = reference_bundle(lab.base / "builds", 1, "1.0.0")
    stale = prepare_release(lab.publisher, artifact, release)
    for signer in (1, 2):
        approve_release(lab.publisher, stale, signer, lab.passphrase)
    lab.publish(2)
    with pytest.raises(UpdateError, match="changed"):
        publish_release(lab.publisher, stale, lab.passphrase)


def test_unavailable_repository_reports_failure_and_keeps_application(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    previous = active_state(client)
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        port = unused.getsockname()[1]
    config = read_json(client / "client.json")
    config["repository_url"] = f"http://127.0.0.1:{port}/"
    write_json(client / "client.json", config)
    result = update(client)
    assert result.outcome == "failed", result.to_dict()
    assert result.reason_code == "DOWNLOAD_FAILED"
    assert active_state(client) == previous


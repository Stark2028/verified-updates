from datetime import timedelta

import pytest
from tuf.api.exceptions import LengthOrHashMismatchError, UnsignedMetadataError

import verified_updates.publisher as publishing
from verified_updates.client import update
from verified_updates.contracts import UpdateError
from verified_updates.reference import reference_bundle


def test_renewal_allows_install_after_timestamp_expiry(repository_lab, monkeypatch):
    lab = repository_lab
    real_clock = publishing.utc_now
    monkeypatch.setattr(publishing, "utc_now", lambda: real_clock() - timedelta(days=2))
    lab.publish(1)
    client = lab.client()
    assert update(client).reason_code == "METADATA_EXPIRED"
    targets_path = lab.publisher / "state" / "targets.json"
    original_targets = targets_path.read_bytes()
    original_timestamp = publishing.authoritative(lab.publisher, "timestamp").signed.version

    monkeypatch.setattr(publishing, "utc_now", real_clock)
    renewed = publishing.renew_metadata(lab.publisher, lab.passphrase)
    assert renewed["timestamp_version"] == original_timestamp + 1
    assert targets_path.read_bytes() == original_targets
    assert update(client).installed_after == 1

    active = (client / "active.json").read_bytes()
    publishing.renew_metadata(lab.publisher, lab.passphrase)
    assert update(client).outcome == "up_to_date"
    assert (client / "active.json").read_bytes() == active


def test_targets_renewal_preserves_release_and_requires_quorum(repository_lab, monkeypatch):
    lab = repository_lab
    real_clock = publishing.utc_now
    monkeypatch.setattr(publishing, "utc_now", lambda: real_clock() - timedelta(days=40))
    release = lab.publish(1)
    original_targets = publishing.authoritative(lab.publisher, "targets").signed
    bundle = lab.base / "builds" / "csv-inspector-1.zip"
    different, _ = reference_bundle(lab.base / "builds", 2, "1.1.0")

    monkeypatch.setattr(publishing, "utc_now", real_clock)
    with pytest.raises(UpdateError, match="targets renewal"):
        publishing.renew_metadata(lab.publisher, lab.passphrase)
    with pytest.raises(LengthOrHashMismatchError):
        publishing.prepare_targets_renewal(lab.publisher, different, release.app_id, release.platform)
    pending = publishing.prepare_targets_renewal(lab.publisher, bundle, release.app_id, release.platform)
    publishing.approve_release(lab.publisher, pending, 1, lab.passphrase)
    with pytest.raises(UnsignedMetadataError):
        publishing.publish_release(lab.publisher, pending, lab.passphrase)
    publishing.approve_release(lab.publisher, pending, 2, lab.passphrase)
    publishing.publish_release(lab.publisher, pending, lab.passphrase)

    renewed = publishing.authoritative(lab.publisher, "targets").signed
    assert renewed.version == original_targets.version + 1
    assert renewed.targets == original_targets.targets
    assert update(lab.client()).installed_after == 1

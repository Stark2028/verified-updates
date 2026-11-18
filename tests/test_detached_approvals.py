import pytest
from tuf.api.exceptions import LengthOrHashMismatchError, UnsignedMetadataError

from verified_updates.approvals import inspect_request, sign_request
from verified_updates.client import initialize_client, update
from verified_updates.contracts import UpdateError
from verified_updates.keys import generate_maintainer_key, load_public_key
from verified_updates.publisher import (
    export_request, import_approval, initialize, inspect_release, prepare_release, publish_release,
)
from verified_updates.reference import reference_bundle
from verified_updates.server import serve_directory


def test_two_external_keys_authorize_a_real_install(tmp_path, monkeypatch):
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    publisher, repository = tmp_path / "publisher", tmp_path / "repository"
    publisher_passphrase = b"test-release-publisher"
    keepers = []
    for index in range(3):
        key_dir = tmp_path / f"maintainer-{index}"
        passphrase = f"test-maintainer-secret-{index}".encode()
        key = load_public_key(generate_maintainer_key(key_dir, passphrase))
        keepers.append((key_dir, passphrase, key))

    with pytest.raises(UpdateError, match="three distinct"):
        initialize(publisher, repository, publisher_passphrase, maintainer_keys=[keepers[0][2]] * 3)
    bootstrap = initialize(publisher, repository, publisher_passphrase,
                           maintainer_keys=[key for _, _, key in keepers])
    assert not (repository / "metadata" / "timestamp.json").exists()
    assert all(not (publisher / "keys" / f"{key.keyid}.pem").exists() for _, _, key in keepers)
    bundle, release = reference_bundle(tmp_path / "builds", 1, "1.0.0")
    pending = prepare_release(publisher, bundle, release)
    request = export_request(publisher, pending, tmp_path / "request.json")
    reviewed = inspect_request(request, bundle, bootstrap)

    def sign(index, digest, output, artifact=bundle):
        directory, passphrase, key = keepers[index]
        sign_request(request, artifact, bootstrap, directory, key.keyid, passphrase, digest, output)

    different_bundle, different_release = reference_bundle(tmp_path / "builds", 2, "1.1.0")
    with pytest.raises(LengthOrHashMismatchError):
        sign(0, reviewed["request_sha256"], tmp_path / "wrong-artifact.json", different_bundle)
    with pytest.raises(UpdateError, match="differs from the inspected"):
        sign(0, "0" * 64, tmp_path / "wrong-digest.json")

    first = tmp_path / "approval-1.json"
    sign(0, reviewed["request_sha256"], first)
    different_pending = prepare_release(publisher, different_bundle, different_release)
    with pytest.raises(UpdateError, match="does not verify"):
        import_approval(publisher, different_pending, first)
    assert import_approval(publisher, pending, first) == 1
    assert import_approval(publisher, pending, first) == 1
    with pytest.raises(UnsignedMetadataError):
        publish_release(publisher, pending, publisher_passphrase)

    second = tmp_path / "approval-2.json"
    sign(1, reviewed["request_sha256"], second)
    assert import_approval(publisher, pending, second) == 2
    assert inspect_release(publisher, pending)["verified_signatures"] == 2
    publish_release(publisher, pending, publisher_passphrase)
    with serve_directory(repository) as url:
        client = tmp_path / "client"
        initialize_client(client, bootstrap, url, release.app_id, release.platform)
        result = update(client)
    assert result.outcome == "updated", result.detail
    assert result.installed_after == 1

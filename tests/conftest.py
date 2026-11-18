from dataclasses import dataclass
from pathlib import Path

import pytest

from verified_updates.client import initialize_client, update
from verified_updates.publisher import initialize, prepare_release, approve_release, publish_release
from verified_updates.reference import reference_bundle
from verified_updates.server import serve_directory


@dataclass
class RepositoryLab:
    base: Path
    publisher: Path
    repository: Path
    bootstrap: Path
    url: str
    passphrase: bytes = b"integration-test-key-passphrase"

    def publish(self, sequence: int, *, broken=False):
        artifact, release = reference_bundle(self.base / "builds", sequence, f"1.{sequence - 1}.0", broken=broken)
        pending = prepare_release(self.publisher, artifact, release)
        approve_release(self.publisher, pending, 1, self.passphrase)
        approve_release(self.publisher, pending, 2, self.passphrase)
        publish_release(self.publisher, pending, self.passphrase)
        return release

    def client(self, name="client", app_id="csv-inspector"):
        client = self.base / name
        initialize_client(client, self.bootstrap, self.url, app_id, "windows-amd64")
        return client

    def installed_client(self, name="client"):
        client = self.client(name)
        result = update(client)
        assert result.outcome == "updated", result.to_dict()
        return client


@pytest.fixture
def repository_lab(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    # Some POSIX environments expose a lowercase proxy variable as well.
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    publisher, repository = tmp_path / "publisher", tmp_path / "repository"
    bootstrap = initialize(publisher, repository, b"integration-test-key-passphrase")
    with serve_directory(repository) as url:
        yield RepositoryLab(tmp_path, publisher, repository, bootstrap, url)


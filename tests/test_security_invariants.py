"""Security-invariant regression tests written independently of the main suite.

These pin the client-side trust and policy boundaries that distinguish the
TUF updater from the lab baselines: the persisted application-sequence
ordering policy, fail-closed handling of corrupted local client state, and
validation of the bootstrapped root before any trust is created.

Each test manipulates trusted *client* state or a *bootstrap* input directly,
which the threat model treats as operator-controlled. That is exactly the
point: an attacker who can rewrite the client host is out of scope, and these
tests prove the client fails closed rather than silently accepting.
"""

from tuf.api.metadata import Metadata
import pytest

from verified_updates.client import active_state, initialize_client, update
from verified_updates.contracts import UpdateError
from verified_updates.publisher import authoritative
from verified_updates.storage import read_json, write_json


@pytest.fixture
def installed_two(repository_lab):
    """A client that has verified and installed releases 1 and 2 (ordering=2)."""
    lab = repository_lab
    lab.publish(1)
    client = lab.client()
    assert update(client).installed_after == 1
    lab.publish(2)
    assert update(client).installed_after == 2
    return lab, client


def test_application_sequence_rollback_is_rejected(installed_two):
    """A signed release below the highest accepted application sequence is rejected.

    This is the application-level ordering policy, distinct from TUF
    metadata-version rollback: the client refuses to move to a lower release
    even when the served metadata is internally consistent and correctly signed.
    """
    lab, client = installed_two
    write_json(client / "ordering.json", {"schema_version": 1, "sequence": 5, "sha256": "0" * 64})
    result = update(client)
    assert result.outcome == "rejected" and result.reason_code == "RELEASE_ROLLBACK", result.to_dict()
    # The installed version is preserved; a rejected update never changes it.
    assert result.installed_before == result.installed_after == 2


def test_reused_sequence_with_new_artifact_is_rejected(installed_two):
    """Reusing a sequence number for a different artifact digest is rejected."""
    lab, client = installed_two
    # Same sequence the server offers (2) but a digest the client never accepted.
    write_json(client / "ordering.json", {"schema_version": 1, "sequence": 2, "sha256": "f" * 64})
    result = update(client)
    assert result.outcome == "rejected" and result.reason_code == "RELEASE_SEQUENCE_REUSED", result.to_dict()
    assert result.installed_after == 2


def test_corrupt_active_state_fails_closed(installed_two, tmp_path):
    """An out-of-schema active pointer is refused, not repaired or accepted."""
    lab, client = installed_two
    state = read_json(client / "active.json")
    state["schema_version"] = 99
    write_json(client / "active.json", state)
    with pytest.raises(UpdateError, match="active-version state"):
        active_state(client)


def test_active_state_directory_escape_fails_closed(installed_two):
    """An active pointer whose directory leaves the version tree is refused."""
    lab, client = installed_two
    state = read_json(client / "active.json")
    state["directory"] = "../evil"
    write_json(client / "active.json", state)
    with pytest.raises(UpdateError):
        active_state(client)


def test_bootstrap_root_must_meet_quorum(repository_lab, tmp_path):
    """A root with fewer than the required signatures is refused before trust is created."""
    lab = repository_lab
    root = Metadata.from_bytes(lab.bootstrap.read_bytes())
    keep = list(root.signatures)[0]
    root.signatures = {keep: root.signatures[keep]}  # drop the second root signature
    weak = tmp_path / "weak-root.json"
    weak.write_bytes(root.to_bytes())
    with pytest.raises(UpdateError, match="[Bb]ootstrap"):
        initialize_client(lab.base / "weak-client", weak, lab.url, "csv-inspector", "windows-amd64")


def test_bootstrap_must_be_a_root_role(repository_lab):
    """Feeding a non-root TUF metadata document as bootstrap is refused."""
    lab = repository_lab
    wrong_role = lab.base / "not-a-root.json"
    wrong_role.write_bytes(authoritative(lab.publisher, "targets").to_bytes())
    with pytest.raises(UpdateError, match="[Bb]ootstrap"):
        initialize_client(lab.base / "wrong-client", wrong_role, lab.url, "csv-inspector", "windows-amd64")


def test_bootstrap_garbage_is_refused(repository_lab):
    lab = repository_lab
    bad = lab.base / "garbage.json"
    bad.write_bytes(b"attacker-supplied bytes, not signed TUF metadata")
    with pytest.raises(UpdateError, match="[Bb]ootstrap"):
        initialize_client(lab.base / "bad-client", bad, lab.url, "csv-inspector", "windows-amd64")

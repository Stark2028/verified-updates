import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from verified_updates.client import update
from verified_updates.contracts import UpdateError
from verified_updates.publisher import (
    PUBLICATION_JOURNAL, approve_release, authoritative, configuration, prepare_release,
)
from verified_updates.reference import reference_bundle
from verified_updates.storage import read_json


# Fault injection lives in this test subprocess. Publication still uses the real
# journal and file writes. Exit 73 identifies exactly the selected write boundary.
INTERRUPT = """
import os, sys
from pathlib import Path
import verified_updates.publisher as publisher
path, operation, detail, point = sys.argv[1:]
path = Path(path)
repository = Path(publisher.configuration(path)['repository'])
atomic_write = publisher.atomic_write
def interrupted_write(destination, data):
    if point == 'before-timestamp' and destination == repository / 'metadata' / 'timestamp.json':
        os._exit(73)
    if point == 'after-timestamp' and destination == path / 'state' / 'snapshot.json':
        os._exit(73)
    atomic_write(destination, data)
publisher.atomic_write = interrupted_write
passphrase = os.environ['VU_KEY_PASSPHRASE'].encode()
if operation == 'publish':
    publisher.publish_release(path, detail, passphrase)
else:
    publisher.rotate_targets_key(path, int(detail), passphrase)
"""


def _interrupt(lab, operation: str, detail: str, point: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", INTERRUPT, str(lab.publisher), operation, detail, point],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "VU_KEY_PASSPHRASE": lab.passphrase.decode()},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 73, result.stderr
    assert (lab.publisher / PUBLICATION_JOURNAL).is_file()


def _recover(lab) -> bool:
    environment = dict(os.environ)
    environment.pop("VU_KEY_PASSPHRASE", None)
    result = subprocess.run(
        [sys.executable, "-m", "verified_updates", "publisher", "recover", "--publisher", str(lab.publisher)],
        cwd=Path(__file__).resolve().parents[1], env=environment, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)["recovered"]


@pytest.mark.parametrize("point, visible", [("before-timestamp", 1), ("after-timestamp", 2)])
def test_publisher_process_exit_replays_exact_release(repository_lab, point, visible):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    bundle, release = reference_bundle(lab.base / "builds", 2, "1.1.0")
    pending = prepare_release(lab.publisher, bundle, release)
    for signer in (1, 2):
        approve_release(lab.publisher, pending, signer, lab.passphrase)

    _interrupt(lab, "publish", pending, point)
    journal = read_json(lab.publisher / PUBLICATION_JOURNAL)
    assert update(client).installed_after == visible
    with pytest.raises(UpdateError, match="publisher recover"):
        prepare_release(lab.publisher, bundle, release)

    assert _recover(lab)
    assert not _recover(lab)
    assert (lab.repository / "metadata" / "timestamp.json").read_bytes() == journal["metadata"]["timestamp"].encode()
    assert read_json(lab.publisher / "pending" / pending / "release.json")["published"]
    assert update(client).installed_after == 2
    lab.publish(3)
    assert update(client).installed_after == 3


def test_interrupted_targets_key_rotation_recovers_for_next_release(repository_lab):
    lab = repository_lab
    lab.publish(1)
    client = lab.installed_client()
    old_key = configuration(lab.publisher)["keys"]["targets"][0]
    _interrupt(lab, "rotate", "1", "before-timestamp")
    assert configuration(lab.publisher)["keys"]["targets"][0] == old_key
    assert _recover(lab)
    current_keys = configuration(lab.publisher)["keys"]["targets"]
    assert old_key not in current_keys
    assert set(authoritative(lab.publisher, "root").signed.roles["targets"].keyids) == set(current_keys)

    lab.publish(2)
    assert update(client).installed_after == 2

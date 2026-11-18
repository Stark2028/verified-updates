import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from verified_updates.baselines import accept_baseline, canonical, publish_baseline
from verified_updates.storage import atomic_write


def test_checksum_replacement_and_valid_signature_replay(repository_lab):
    lab = repository_lab
    key = Ed25519PrivateKey.generate()
    old = publish_baseline(lab.repository, b"first harmless release", 1, key)
    assert accept_baseline(lab.url, key.public_key())["accepted"]
    publish_baseline(lab.repository, b"second harmless release", 2, key)
    assert accept_baseline(lab.url, key.public_key())["sequence"] == 2
    changed = json.loads((lab.repository / "baseline" / "manifest.json").read_bytes())
    # An attacker reuses the old file digest but retains the new signature.
    old_data = json.loads(old)
    changed["signed"] = old_data["signed"]
    atomic_write(lab.repository / "baseline" / "application.zip", b"first harmless release")
    atomic_write(lab.repository / "baseline" / "manifest.json", canonical(changed))
    assert accept_baseline(lab.url, None)["accepted"]
    assert accept_baseline(lab.url, key.public_key()) == {"accepted": False, "reason": "SIGNATURE_INVALID"}
    # The original signature is valid, despite being an obsolete release.
    atomic_write(lab.repository / "baseline" / "manifest.json", old)
    assert accept_baseline(lab.url, key.public_key())["sequence"] == 1


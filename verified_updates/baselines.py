"""Lab-only artifact acceptance baselines; never selectable by the real updater.

These intentionally incomplete verifiers accept bytes, not installed programs.
Their purpose is a controlled comparison of authentication and replay policy.
"""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from verified_updates.storage import atomic_write


def canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def publish_baseline(repository: Path, artifact: bytes, sequence: int, key: Ed25519PrivateKey) -> bytes:
    manifest = {"sequence": sequence, "length": len(artifact), "sha256": hashlib.sha256(artifact).hexdigest()}
    envelope = {"signed": manifest, "signature": key.sign(canonical(manifest)).hex()}
    encoded = canonical(envelope)
    atomic_write(repository / "baseline" / "application.zip", artifact)
    atomic_write(repository / "baseline" / "manifest.json", encoded)
    return encoded


def accept_baseline(repository_url: str, public_key: Ed25519PublicKey | None) -> dict:
    """None = unauthenticated checksum, key = signature without replay policy."""
    if urlsplit(repository_url).hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("Deliberately incomplete comparison clients are restricted to the local lab.")
    # The local experiment does not send loopback requests through a proxy.
    opener = build_opener(ProxyHandler({}))

    def fetch(path: str, limit: int) -> bytes:
        with opener.open(Request(repository_url.rstrip("/") + "/baseline/" + path), timeout=5) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Comparison artifact exceeds its lab limit.")
        return data

    envelope = json.loads(fetch("manifest.json", 65536))
    manifest = envelope["signed"]
    if public_key is not None:
        try:
            public_key.verify(bytes.fromhex(envelope["signature"]), canonical(manifest))
        except (InvalidSignature, ValueError):
            return {"accepted": False, "reason": "SIGNATURE_INVALID"}
    artifact = fetch("application.zip", 64 * 1024 * 1024)
    if len(artifact) != manifest["length"] or hashlib.sha256(artifact).hexdigest() != manifest["sha256"]:
        return {"accepted": False, "reason": "ARTIFACT_MISMATCH"}
    return {"accepted": True, "reason": "CHECKS_PASSED", "sequence": manifest["sequence"], "sha256": manifest["sha256"]}


def run_comparison(repository: Path, url: str, artifact_v1: bytes, artifact_v2: bytes, tuf_cases: list[dict]) -> list[dict]:
    key = Ed25519PrivateKey.generate()
    old_manifest = publish_baseline(repository, artifact_v1, 1, key)
    rows = []

    def measure(name: str, expected: tuple[bool, bool], tuf_case: str):
        unsigned = accept_baseline(url, None)
        signed = accept_baseline(url, key.public_key())
        reference = next(case for case in tuf_cases if case["scenario"] == tuf_case)
        tuf_accepted = reference["actual"]["outcome"] in ("updated", "up_to_date")
        expected_tuf = name == "genuine_release"
        rows.append({
            "scenario": name, "unsigned_checksum": unsigned, "signature_only": signed,
            "tuf": {"accepted": tuf_accepted, "reason": reference["actual"]["reason_code"], "source_run_id": reference["actual"]["run_id"]},
            "passed": (unsigned["accepted"], signed["accepted"]) == expected and tuf_accepted == expected_tuf and reference["passed"],
        })

    measure("genuine_release", (True, True), "genuine_release_v1")
    publish_baseline(repository, artifact_v2, 2, key)
    # Attacker can replace the file and recompute an unsigned checksum, but
    # cannot replace its pinned-key signature. Flip bytes identically to TUF.
    changed = bytearray(artifact_v2)
    changed[len(changed) // 2] ^= 1
    altered = bytes(changed)
    envelope = json.loads((repository / "baseline" / "manifest.json").read_bytes())
    envelope["signed"]["sha256"] = hashlib.sha256(altered).hexdigest()
    atomic_write(repository / "baseline" / "application.zip", altered)
    atomic_write(repository / "baseline" / "manifest.json", canonical(envelope))
    measure("file_and_unsigned_checksum_replacement", (True, False), "artifact_substitution")
    # Both baselines have observed v2, but neither retains a release-ordering
    # policy. A correct old signature is consequently still accepted.
    publish_baseline(repository, artifact_v2, 2, key)
    assert accept_baseline(url, None)["accepted"]
    assert accept_baseline(url, key.public_key())["accepted"]
    atomic_write(repository / "baseline" / "application.zip", artifact_v1)
    atomic_write(repository / "baseline" / "manifest.json", old_manifest)
    measure("replay_previously_signed_release", (True, True), "metadata_rollback_after_process_restart")
    return rows


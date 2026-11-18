"""Approval files exchanged between the publisher and offline maintainers."""

from hashlib import sha256
from pathlib import Path

from securesystemslib.signer import Signature
from tuf.api.metadata import Metadata, Root, Targets

from verified_updates.contracts import Release, UpdateError
from verified_updates.installer import MAX_ARTIFACT_BYTES
from verified_updates.keys import load_signer
from verified_updates.publisher import utc_now
from verified_updates.storage import write_json


def _review_request(request: Path, artifact: Path, trusted_root: Path):
    root = Metadata.from_file(str(trusted_root))
    if not isinstance(root.signed, Root) or root.signed.is_expired(utc_now()):
        raise UpdateError("INVALID_ROOT", "Use current, independently trusted TUF root metadata.")
    root.signed.verify_delegate("root", root.signed_bytes, root.signatures)
    metadata = Metadata.from_file(str(request))
    if not isinstance(metadata.signed, Targets) or metadata.signed.is_expired(utc_now()):
        raise UpdateError("INVALID_REQUEST", "Expected current TUF targets metadata.")
    if metadata.signed.delegations is not None or len(metadata.signed.targets) != 1:
        raise UpdateError("INVALID_REQUEST", "A detached signing request must authorize exactly one artifact with no delegated roles.")
    target = next(iter(metadata.signed.targets.values()))
    release = Release.from_custom(target.custom)
    if release.target_path != target.path or target.length > MAX_ARTIFACT_BYTES or set(target.hashes) != {"sha256"}:
        raise UpdateError("INVALID_REQUEST", "Target identity, size, or digest policy is invalid.")
    with artifact.open("rb") as stream:
        target.verify_length_and_hashes(stream)
    summary = {
        "release": target.custom["verified_updates"],
        "artifact_sha256": target.hashes["sha256"],
        "artifact_bytes": target.length,
        "targets_version": metadata.signed.version,
        "targets_expires": metadata.signed.expires.isoformat(),
        "request_sha256": sha256(metadata.signed_bytes).hexdigest(),
    }
    return root.signed, metadata, summary


def inspect_request(request: Path, artifact: Path, trusted_root: Path) -> dict:
    return _review_request(request, artifact, trusted_root)[2]


def sign_request(request: Path, artifact: Path, trusted_root: Path, key_dir: Path,
                 key_id: str, passphrase: bytes, expected_digest: str, output: Path) -> dict:
    root, metadata, summary = _review_request(request, artifact, trusted_root)
    if key_id not in root.roles["targets"].keyids:
        raise UpdateError("UNAUTHORIZED_SIGNER", "This key cannot authorize releases under the supplied root.")
    if expected_digest != summary["request_sha256"]:
        raise UpdateError("REQUEST_CHANGED", "The signing request differs from the inspected request digest.")
    if output.exists():
        raise UpdateError("OUTPUT_EXISTS", "Choose a new path for the detached approval.")
    signer = load_signer(key_dir, key_id, passphrase)
    signature: Signature = signer.sign(metadata.signed_bytes)
    write_json(output, signature.to_dict())
    return {"approval": str(output.resolve()), "keyid": key_id, **summary}

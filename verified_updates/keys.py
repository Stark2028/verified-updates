"""Encrypted Ed25519 publisher keys, kept outside the public repository."""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from securesystemslib.signer import CryptoSigner, SSlibKey

from verified_updates.contracts import UpdateError
from verified_updates.storage import atomic_write


def generate_maintainer_key(directory: Path, passphrase: bytes) -> Path:
    signer = generate_signer(directory, passphrase)
    public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(signer.public_key.keyval["public"]))
    path = directory / f"{signer.public_key.keyid}.pub.pem"
    atomic_write(path, public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return path


def load_public_key(path: Path) -> SSlibKey:
    try:
        public = serialization.load_pem_public_key(path.read_bytes())
    except ValueError as exc:
        raise UpdateError("INVALID_KEY", "Expected a PEM-encoded Ed25519 public key.") from exc
    if not isinstance(public, Ed25519PublicKey):
        raise UpdateError("INVALID_KEY", "Expected an Ed25519 public key.")
    return SSlibKey.from_crypto(public)


def generate_signer(directory: Path, passphrase: bytes) -> CryptoSigner:
    if len(passphrase) < 12:
        raise UpdateError("WEAK_PASSPHRASE", "Use a key-file passphrase of at least 12 bytes.")
    private = Ed25519PrivateKey.generate()
    signer = CryptoSigner(private)
    encrypted = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(passphrase),
    )
    atomic_write(directory / f"{signer.public_key.keyid}.pem", encrypted)
    return signer


def load_signer(directory: Path, keyid: str, passphrase: bytes) -> CryptoSigner:
    if len(keyid) != 64 or any(c not in "0123456789abcdef" for c in keyid):
        raise UpdateError("INVALID_KEY", "Invalid publisher key identifier.")
    try:
        private = serialization.load_pem_private_key((directory / f"{keyid}.pem").read_bytes(), passphrase)
    except (ValueError, TypeError) as exc:
        raise UpdateError("KEY_UNLOCK_FAILED", "Unable to decrypt the selected private key.") from exc
    if not isinstance(private, Ed25519PrivateKey):
        raise UpdateError("INVALID_KEY", "Expected an Ed25519 signing key.")
    signer = CryptoSigner(private)
    if signer.public_key.keyid != keyid:
        raise UpdateError("INVALID_KEY", "Key-file contents do not match the selected public identity.")
    return signer


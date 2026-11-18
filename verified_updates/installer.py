"""Validate, stage and activate source bundles without overwriting running files."""

from dataclasses import asdict
import json
from pathlib import Path
import stat
import subprocess
import sys
from uuid import uuid4
import zipfile

from verified_updates.contracts import Release, UpdateError, relative_path
from verified_updates.storage import read_json, write_json


MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_UNPACKED_BYTES = 256 * 1024 * 1024
MAX_FILES = 2048
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}


def _archive_path(name: str) -> str:
    name = relative_path(name)
    for part in name.split("/"):
        if part.endswith((" ", ".")) or part.split(".")[0].upper() in WINDOWS_RESERVED:
            raise UpdateError("INVALID_PACKAGE", f"Unsupported Windows archive path: {name!r}")
        if any(ord(c) < 32 or c in '<>"|?*' for c in part):
            raise UpdateError("INVALID_PACKAGE", f"Invalid archive path: {name!r}")
    return name


def unpack(artifact: Path, destination: Path, release: Release) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(artifact) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES or sum(x.file_size for x in infos) > MAX_UNPACKED_BYTES:
                raise UpdateError("PACKAGE_TOO_LARGE", "Archive exceeds local extraction limits.")
            names: set[str] = set()
            for info in infos:
                if info.flag_bits & 1:
                    raise UpdateError("INVALID_PACKAGE", "Password-encrypted ZIP entries are unsupported.")
                # ZipInfo normalizes Windows separators and truncates NULs in
                # filename. Validate the original stored name at this boundary.
                raw_name = info.orig_filename
                name = _archive_path(raw_name[:-1] if raw_name.endswith("/") else raw_name)
                if name.casefold() in names:
                    raise UpdateError("INVALID_PACKAGE", "Archive contains duplicate or case-conflicting paths.")
                names.add(name.casefold())
                mode = stat.S_IFMT(info.external_attr >> 16)
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise UpdateError("INVALID_PACKAGE", "Archive links and special files are unsupported.")
                target = destination / name
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise UpdateError("INVALID_PACKAGE", "Archive path escapes the staging directory.")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as output:
                    copied = 0
                    while chunk := source.read(64 * 1024):
                        copied += len(chunk)
                        if copied > info.file_size or copied > MAX_UNPACKED_BYTES:
                            raise UpdateError("PACKAGE_TOO_LARGE", "Archive expands beyond its declared size.")
                        output.write(chunk)
            manifest = read_json(destination / "release.json")
            if Release.from_custom({"verified_updates": manifest}) != release:
                raise UpdateError("INVALID_PACKAGE", "Bundle identity differs from the signed release metadata.")
            if not (destination / release.entrypoint).is_file():
                raise UpdateError("INVALID_PACKAGE", "Declared application entrypoint is missing.")
    except (zipfile.BadZipFile, FileNotFoundError, json.JSONDecodeError, UnicodeError) as exc:
        raise UpdateError("INVALID_PACKAGE", f"Invalid release archive: {exc}") from exc


def activate(client: Path, artifact: Path, release: Release, digest: str) -> None:
    directory_name = f"{release.sequence}-{uuid4().hex}"
    staged = client / "versions" / directory_name
    unpack(artifact, staged, release)
    try:
        health = subprocess.run(
            [sys.executable, "-I", str((staged / release.entrypoint).resolve()), "--self-test"],
            cwd=staged, capture_output=True, text=True, timeout=10, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UpdateError("INSTALL_SELF_TEST_FAILED", "New application self-test timed out; active version was retained.") from exc
    if health.returncode != 0:
        raise UpdateError("INSTALL_SELF_TEST_FAILED", f"New application self-test exited {health.returncode}; active version was retained.")
    # This is the only activation commit. Old directories remain available.
    write_json(client / "active.json", {
        "schema_version": 1, "directory": directory_name,
        "release": release.to_custom(), "sha256": digest,
    })


def active_state(client: Path) -> dict | None:
    path = client / "active.json"
    if not path.exists():
        return None
    state = read_json(path)
    if state.get("schema_version") != 1:
        raise UpdateError("INVALID_CLIENT_STATE", "Unsupported active-version state.")
    Release.from_custom(state["release"])
    relative_path(state["directory"])
    directory = (client / "versions" / state["directory"]).resolve()
    if not directory.is_relative_to((client / "versions").resolve()):
        raise UpdateError("INVALID_CLIENT_STATE", "Active version is outside the installation directory.")
    return state


def run_installed(client: Path, arguments: list[str]) -> int:
    state = active_state(client)
    if state is None:
        raise UpdateError("NOT_INSTALLED", "No verified application is installed.")
    release = Release.from_custom(state["release"])
    application = (client / "versions" / state["directory"] / release.entrypoint).resolve()
    return subprocess.call([sys.executable, "-I", str(application), *arguments])


def build_bundle(source: Path, destination: Path, release: Release) -> Path:
    """Package the first single-file reference application and its identity."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(source, release.entrypoint)
        archive.writestr("release.json", json.dumps({"schema_version": 1, **asdict(release)}))
    return destination


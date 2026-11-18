"""A fresh Windows desktop update workflow through the public launcher."""

import json
from pathlib import Path
import secrets
import subprocess
import sys
from uuid import uuid4

from demo_app import bundle_gui
from verified_updates.contracts import UpdateError
from verified_updates.lab import _client_environment, public_artifact
from verified_updates.publisher import approve_release, initialize, prepare_release, publish_release
from verified_updates.server import serve_directory


def run_desktop_demo(directory: Path | None, show: bool = False) -> dict:
    run = (directory or Path(".runtime") / f"desktop-{uuid4().hex[:12]}").resolve()
    run.mkdir(parents=True, exist_ok=False)
    publisher, repository, client = (run / name for name in ("publisher", "repository", "client"))
    passphrase = secrets.token_urlsafe(32).encode()
    bootstrap = initialize(publisher, repository, passphrase)
    environment = _client_environment()

    def publish(sequence: int, version: str) -> None:
        bundle, release = bundle_gui.gui_bundle(run / "builds", sequence, version)
        draft = prepare_release(publisher, bundle, release)
        for signer in (1, 2):
            approve_release(publisher, draft, signer, passphrase)
        publish_release(publisher, draft, passphrase)

    def launcher(*args: str, expected: int = 0) -> list[dict]:
        command = [sys.executable, "-m", "verified_updates", "gui-launcher", "--client-dir", str(client), *args]
        result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=120)
        if result.returncode != expected:
            raise UpdateError("DESKTOP_DEMO_FAILED", result.stdout.strip() or result.stderr.strip())
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def installed_version(version: str, summaries: bool) -> dict:
        result, = launcher("--gui", "--app-arg=--version")
        if result["version"] != version or result["numeric_summaries"] != summaries:
            raise UpdateError("DESKTOP_DEMO_FAILED", f"Launcher returned unexpected version or feature state: {result}")
        return result

    def show_window(message: str) -> None:
        if show:
            print(message, flush=True)
            sample = Path(bundle_gui.__file__).with_name("sample.csv").resolve()
            command = [sys.executable, "-m", "verified_updates", "gui-launcher", "--client-dir", str(client),
                       "--gui", f"--app-arg={sample}"]
            if subprocess.run(command, env=environment).returncode:
                raise UpdateError("DESKTOP_DEMO_FAILED", "The installed desktop app could not open.")

    with serve_directory(repository) as url:
        publish(1, "1.0.0")
        launcher("--install", "--bootstrap", str(bootstrap), "--repository-url", url, "--status")
        first = installed_version("1.0.0", False)
        show_window("Version 1 is installed. Close this window to offer version 2.")

        publish(2, "1.1.0")
        # This disposable fixture changes one byte in the published ZIP.
        artifact = public_artifact(publisher)
        with artifact.open("r+b") as stream:
            offset = artifact.stat().st_size // 2
            stream.seek(offset)
            original = stream.read(1)
            stream.seek(offset)
            stream.write(bytes([original[0] ^ 1]))
        try:
            rejected, = launcher("--check-updates", "--status", expected=3)
            if rejected["update"].get("reason_code") != "TARGET_INTEGRITY_FAILED":
                raise UpdateError("DESKTOP_DEMO_FAILED", f"Unexpected rejection: {rejected}")
            retained = installed_version("1.0.0", False)
            show_window("The changed bundle was rejected. Version 1 still opens. Close it to restore the authorized bundle.")
        finally:
            with artifact.open("r+b") as stream:
                stream.seek(offset)
                stream.write(original)

        launcher("--check-updates", "--status")
        second = installed_version("1.1.0", True)
        show_window("Version 2 is active. The numeric summaries are visible for the sample CSV.")

    return {"directory": str(run), "initial": first, "rejection": rejected["update"]["reason_code"],
            "retained": retained, "updated": second}

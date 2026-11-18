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
from verified_updates.storage import read_json


def _open_window(client: Path, sample: Path, environment: dict[str, str]) -> None:
    command = [sys.executable, "-m", "verified_updates", "gui-launcher", "--client-dir", str(client),
               "--gui", f"--app-arg={sample}"]
    if subprocess.run(command, env=environment).returncode:
        raise UpdateError("DESKTOP_DEMO_FAILED", "The installed desktop app could not open.")


def run_desktop_demo(directory: Path | None, show: bool = False) -> dict:
    run = (directory or Path(".runtime") / f"desktop-{uuid4().hex[:12]}").resolve()
    run.mkdir(parents=True, exist_ok=False)
    publisher, repository, client = (run / name for name in ("publisher", "repository", "client"))
    passphrase = secrets.token_urlsafe(32).encode()
    bootstrap = initialize(publisher, repository, passphrase)
    environment = _client_environment()
    sample = Path(bundle_gui.__file__).with_name("sample.csv").resolve()

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

    def show_update(instructions: str, outcome: str, sequence: int, reason: str | None = None) -> dict:
        events = client / "events"
        before = set(events.glob("*.json"))
        print(instructions, flush=True)
        _open_window(client, sample, environment)
        new_events = [read_json(path) for path in set(events.glob("*.json")) - before]
        if not new_events:
            raise UpdateError("DEMO_UPDATE_REQUIRED", "Click Check for updates and show its result before closing the app. Start the demo again to retry.")
        for event in new_events:
            if (event["outcome"] == outcome and event["installed_after"] == sequence
                    and (reason is None or event["reason_code"] == reason)):
                print(event["detail"], flush=True)
                return event
        reason_codes = ", ".join(sorted({event["reason_code"] for event in new_events}))
        raise UpdateError("DESKTOP_DEMO_FAILED", f"Unexpected update results: {reason_codes}")

    with serve_directory(repository) as url:
        publish(1, "1.0.0")
        launcher("--install", "--bootstrap", str(bootstrap), "--repository-url", url, "--status")
        first = installed_version("1.0.0", False)
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
            if show:
                rejected = show_update(
                    "1. Show version 1.0.0 in the title bar. A changed v2 ZIP is on the local server.\n"
                    "   Click Check for updates. Show the rejection at the bottom and the unchanged title. Then close the window.",
                    "rejected", 1, "TARGET_INTEGRITY_FAILED",
                )
            else:
                response, = launcher("--check-updates", "--status", expected=3)
                rejected = response["update"]
            if rejected.get("reason_code") != "TARGET_INTEGRITY_FAILED":
                raise UpdateError("DESKTOP_DEMO_FAILED", f"Unexpected rejection: {rejected}")
            retained = installed_version("1.0.0", False)
        finally:
            with artifact.open("r+b") as stream:
                stream.seek(offset)
                stream.write(original)

        if show:
            show_update(
                "2. The original signed release bundle is back. Version 1.0.0 opens again.\n"
                "   Click Check for updates. Show the success message, then close the window to run the installed update.",
                "updated", 2,
            )
        else:
            launcher("--check-updates", "--status")
        second = installed_version("1.1.0", True)
        if show:
            print("3. Show version 1.1.0 in the title bar and the new Numeric summaries panel. Close when finished.", flush=True)
            _open_window(client, sample, environment)

    return {"directory": str(run), "initial": first, "rejection": rejected["reason_code"],
            "retained": retained, "updated": second}

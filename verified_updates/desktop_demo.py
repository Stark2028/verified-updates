"""A fresh Windows desktop update workflow through the public launcher."""

import json
from pathlib import Path
import secrets
import subprocess
import sys
from uuid import uuid4

from tuf.api.exceptions import RepositoryError

from demo_app import bundle_gui
from verified_updates.contracts import UpdateError
from verified_updates.installer import active_state
from verified_updates.lab import _client_environment, public_artifact
from verified_updates.publisher import approve_release, initialize, inspect_release, prepare_release, publish_release
from verified_updates.server import serve_directory
from verified_updates.storage import atomic_write, read_json


def _open_window(client: Path, sample: Path, environment: dict[str, str]) -> None:
    command = [sys.executable, "-m", "verified_updates", "gui-launcher", "--client-dir", str(client),
               "--gui", f"--app-arg={sample}"]
    if subprocess.run(command, env=environment).returncode:
        raise UpdateError("DESKTOP_DEMO_FAILED", "The installed desktop app could not open.")


def _change_artifact(path: Path) -> tuple[int, bytes]:
    with path.open("r+b") as stream:
        offset = path.stat().st_size // 2
        stream.seek(offset)
        original = stream.read(1)
        stream.seek(offset)
        stream.write(bytes([original[0] ^ 1]))
    return offset, original


def _restore_artifact(path: Path, offset: int, original: bytes) -> None:
    with path.open("r+b") as stream:
        stream.seek(offset)
        stream.write(original)


OPERATOR_COMMANDS = """\
  prepare       Build v2 and show its signed-metadata draft
  approve 1     Sign the draft with release key 1
  approve 2     Sign the draft with release key 2
  publish       Attempt publication with the approvals received so far
  change        Change one byte in the served v2 ZIP
  restore       Restore the genuine ZIP and current metadata
  replay        Serve the old, correctly signed v1 metadata after v2 is installed
  open          Open the installed app and use Check for updates
  check         Run the same updater and print its recorded decision
  status        Show the active version
  help          List the available commands
  exit          Stop the local server
"""


def _operator(run: Path, passphrase: bytes, sample: Path, environment: dict[str, str], launcher) -> dict:
    publisher, client = run / "publisher", run / "client"
    timestamp = run / "repository" / "metadata" / "timestamp.json"
    initial_timestamp = timestamp.read_bytes()
    current_timestamp = initial_timestamp
    changed_artifact: tuple[Path, int, bytes] | None = None
    replaying = False
    pending = None
    published = False
    print("Version 1 is installed. Control the publisher and local repository from this prompt.", flush=True)
    print(OPERATOR_COMMANDS, flush=True)
    try:
        while True:
            try:
                command = input("updates> ").strip().lower()
            except EOFError:
                break
            if command == "exit":
                break
            try:
                if command == "help":
                    print(OPERATOR_COMMANDS)
                elif command == "prepare":
                    if pending is not None:
                        print("Version 2 already has a draft in this session.")
                        continue
                    bundle, release = bundle_gui.gui_bundle(run / "builds", 2, "1.1.0")
                    pending = prepare_release(publisher, bundle, release)
                    draft = inspect_release(publisher, pending)
                    print(f"Prepared {draft['release']['version']}. SHA-256 {draft['sha256']}")
                    print(f"Approvals {draft['verified_signatures']}/{draft['required_signatures']}.")
                elif command in ("approve 1", "approve 2", "publish"):
                    if pending is None or published:
                        print("Prepare an unpublished v2 draft first.")
                        continue
                    if command == "publish":
                        target = publish_release(publisher, pending, passphrase)
                        published = True
                        current_timestamp = timestamp.read_bytes()
                        print(f"Publication accepted. The repository now offers v2 at {target}.")
                    else:
                        signer = int(command[-1])
                        approve_release(publisher, pending, signer, passphrase)
                        draft = inspect_release(publisher, pending)
                        print(f"Key {signer} signed. Verified approvals {draft['verified_signatures']}/{draft['required_signatures']}.")
                elif command == "change":
                    if not published or changed_artifact is not None or replaying:
                        print("Publish v2 and restore any existing repository changes first.")
                        continue
                    artifact = public_artifact(publisher)
                    changed_artifact = (artifact, *_change_artifact(artifact))
                    print("Changed one byte in the served ZIP. Signed metadata still commits to the genuine ZIP.")
                elif command == "replay":
                    if active_state(client)["release"]["verified_updates"]["sequence"] != 2 or changed_artifact is not None or replaying:
                        print("Install genuine v2 and restore any existing repository changes first.")
                        continue
                    atomic_write(timestamp, initial_timestamp)
                    replaying = True
                    print("The repository now serves its original v1 timestamp. The old signature is still valid.")
                elif command == "restore":
                    if changed_artifact is not None:
                        _restore_artifact(*changed_artifact)
                        changed_artifact = None
                    if replaying:
                        atomic_write(timestamp, current_timestamp)
                        replaying = False
                    print("The repository is serving the genuine current files.")
                elif command == "open":
                    print("The app title shows the installed version. Close it to return here.", flush=True)
                    _open_window(client, sample, environment)
                elif command == "check":
                    response = launcher("--check-updates", "--status", expected=None)
                    event = response[0]["update"]
                    reason = event.get("reason_code", event.get("error", "UPDATE_FAILED"))
                    print(f"{reason}. {event.get('detail', '')}")
                    if "installed_after" in event:
                        print(f"Active release sequence {event['installed_after']}.")
                elif command == "status":
                    release = active_state(client)["release"]["verified_updates"]
                    print(f"Installed version {release['version']} (sequence {release['sequence']}).")
                elif command:
                    print("Unknown command. Type help to see the available commands.")
            except (UpdateError, RepositoryError, OSError, subprocess.TimeoutExpired) as exc:
                print(f"{getattr(exc, 'code', type(exc).__name__)}: {exc}")
    finally:
        if changed_artifact is not None:
            _restore_artifact(*changed_artifact)
        if replaying:
            atomic_write(timestamp, current_timestamp)
    return {"directory": str(run), "active": active_state(client)}


def run_desktop_demo(directory: Path | None, show: bool = False, operator: bool = False) -> dict:
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

    def launcher(*args: str, expected: int | None = 0) -> list[dict]:
        command = [sys.executable, "-m", "verified_updates", "gui-launcher", "--client-dir", str(client), *args]
        result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=120)
        if result.returncode not in ((0, 2, 3, 4) if expected is None else (expected,)):
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
        if operator:
            return _operator(run, passphrase, sample, environment, launcher)
        first = installed_version("1.0.0", False)
        publish(2, "1.1.0")
        # This disposable fixture changes one byte in the published ZIP.
        artifact = public_artifact(publisher)
        offset, original = _change_artifact(artifact)
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
            _restore_artifact(artifact, offset, original)

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

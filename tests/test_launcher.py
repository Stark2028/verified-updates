"""Desktop GUI reference application on the real TUF update pipeline.

These tests prove that the Tkinter CSV Inspector bundles update and restart
correctly through the verified-updates client (the same code the CLI demo uses),
and that a tampered GUI release is rejected while the working version is kept.
Headless CLI paths are tested directly so the suite stays portable; the
interactive widget self-test is guarded behind a display availability check.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from demo_app import csv_viewer_gui
from demo_app.bundle_gui import gui_bundle
from verified_updates.client import initialize_client, update
from verified_updates.lab import public_artifact
from verified_updates.publisher import (
    approve_release, initialize, prepare_release, publish_release,
)
from verified_updates.server import serve_directory
from verified_updates.storage import atomic_write, read_json

ROOT = Path(__file__).resolve().parents[1]


def _headless_app(path: Path, *args: str) -> dict:
    """Run a generated app file's headless CLI and parse its JSON output."""
    completed = subprocess.run([sys.executable, str(path), *args],
                               capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


def test_gui_app_headless_version_and_export(tmp_path):
    """Sequence-1 bundle has no summaries; a generated sequence-2 module does."""
    builds = tmp_path / "b"
    gui_bundle(builds, 1, "1.0.0")
    gui_bundle(builds, 2, "1.1.0")
    src1, src2 = builds / "csv_viewer_1.py", builds / "csv_viewer_2.py"

    info1 = _headless_app(src1, "--version")
    assert info1["version"] == "1.0.0" and info1["numeric_summaries"] is False

    info2 = _headless_app(src2, "--version")
    assert info2["version"] == "1.1.0" and info2["numeric_summaries"] is True

    # File + export runs without a display and preserves the source file.
    data = tmp_path / "people.csv"
    data.write_text("name,score\nAlice,91\nBob,84\n", encoding="utf-8")
    out = tmp_path / "filtered.csv"
    result = _headless_app(src2, str(data), "--contains", "Alice", "--export", str(out))
    assert result["row_count"] == 1 and result["exported_to"] == str(out)
    assert "score" in result["numeric_summaries"]


def test_gui_broken_bundle_fails_self_test(tmp_path):
    """A broken authorized release makes the installer's pre-commit self-test fail."""
    builds = tmp_path / "b"
    broken_zip, _ = gui_bundle(builds, 2, "1.1.0", broken=True)
    import zipfile
    with zipfile.ZipFile(broken_zip) as archive:
        payload = archive.read("app.py")
    generated = tmp_path / "broken_app.py"
    generated.write_bytes(payload)
    completed = subprocess.run([sys.executable, str(generated), "--self-test"],
                               capture_output=True, text=True, timeout=60)
    assert completed.returncode == 17


def test_gui_updates_restart_into_new_version(tmp_path, monkeypatch):
    """Install seq1, publish seq2, update, and restart into the new GUI version."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    publisher, repository = tmp_path / "publisher", tmp_path / "repository"
    passphrase = b"launcher-test-key-passphrase"
    bootstrap = initialize(publisher, repository, passphrase)

    with serve_directory(repository) as url:
        # Publish only sequence 1; the client installs it first.
        artifact1, release1 = gui_bundle(tmp_path / "builds", 1, "1.0.0")
        pending1 = prepare_release(publisher, artifact1, release1)
        approve_release(publisher, pending1, 1, passphrase)
        approve_release(publisher, pending1, 2, passphrase)
        publish_release(publisher, pending1, passphrase)

        client = tmp_path / "client"
        initialize_client(client, bootstrap, url, "csv-inspector", "windows-amd64")
        first = update(client)
        assert first.outcome == "updated" and first.installed_after == 1

        # Now publish sequence 2 and update again; restart into the new GUI.
        artifact2, release2 = gui_bundle(tmp_path / "builds", 2, "1.1.0")
        pending2 = prepare_release(publisher, artifact2, release2)
        approve_release(publisher, pending2, 1, passphrase)
        approve_release(publisher, pending2, 2, passphrase)
        publish_release(publisher, pending2, passphrase)

        second = update(client)
        assert second.outcome == "updated" and second.installed_after == 2

        active = read_json(client / "active.json")
        assert active["release"]["verified_updates"]["version"] == "1.1.0"

        # Restart into the new version via a fresh, isolated process (headless).
        app = client / "versions" / active["directory"] / "app.py"
        info = _headless_app(app, "--version")
        assert info["version"] == "1.1.0" and info["numeric_summaries"] is True


def test_gui_rejects_tampered_release(tmp_path, monkeypatch):
    """An attacker who rewrites a served GUI release is rejected; active version stays."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    publisher, repository = tmp_path / "publisher", tmp_path / "repository"
    passphrase = b"launcher-test-key-passphrase"
    bootstrap = initialize(publisher, repository, passphrase)

    with serve_directory(repository) as url:
        artifact1, release1 = gui_bundle(tmp_path / "builds", 1, "1.0.0")
        pending = prepare_release(publisher, artifact1, release1)
        approve_release(publisher, pending, 1, passphrase)
        approve_release(publisher, pending, 2, passphrase)
        publish_release(publisher, pending, passphrase)

        client = tmp_path / "client"
        initialize_client(client, bootstrap, url, "csv-inspector", "windows-amd64")
        first = update(client)
        assert first.outcome == "updated" and first.installed_after == 1

        # Publish a second release, then tamper the NEW served artifact.
        artifact2, release2 = gui_bundle(tmp_path / "builds", 2, "1.1.0")
        pending2 = prepare_release(publisher, artifact2, release2)
        approve_release(publisher, pending2, 1, passphrase)
        approve_release(publisher, pending2, 2, passphrase)
        publish_release(publisher, pending2, passphrase)

        served = public_artifact(publisher)
        active_dir = read_json(client / "active.json")["directory"]
        raw = bytearray(served.read_bytes())
        raw[len(raw) // 2] ^= 1
        atomic_write(served, bytes(raw))

        result = update(client)
        assert result.outcome == "rejected" and result.reason_code == "TARGET_INTEGRITY_FAILED"
        assert read_json(client / "active.json")["directory"] == active_dir
        assert result.installed_before == result.installed_after == 1


@pytest.mark.skipif(not _display_available(), reason="No interactive display available for the widget self-test.")
def test_gui_self_test_opens_widget(tmp_path, monkeypatch):
    """The installed GUI app's --self-test actually constructs the Tk widgets."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    publisher, repository = tmp_path / "publisher", tmp_path / "repository"
    passphrase = b"launcher-test-key-passphrase"
    bootstrap = initialize(publisher, repository, passphrase)
    with serve_directory(repository) as url:
        artifact, release = gui_bundle(tmp_path / "builds", 1, "1.0.0")
        pending = prepare_release(publisher, artifact, release)
        approve_release(publisher, pending, 1, passphrase)
        approve_release(publisher, pending, 2, passphrase)
        publish_release(publisher, pending, passphrase)
        client = tmp_path / "client"
        initialize_client(client, bootstrap, url, "csv-inspector", "windows-amd64")
        assert update(client).outcome == "updated"
        completed = subprocess.run(
            [sys.executable, "-I", str(client / "versions" / read_json(client / "active.json")["directory"] / "app.py"),
             "--self-test"], capture_output=True, text=True, cwd=ROOT, timeout=60)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert json.loads(completed.stdout)["self_test"] == "passed"


def test_launcher_delegates_update_to_verified_cli(tmp_path, monkeypatch):
    """The thin launcher routes installs/updates through the verified CLI only."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    publisher, repository = tmp_path / "publisher", tmp_path / "repository"
    passphrase = b"launcher-test-key-passphrase"
    bootstrap = initialize(publisher, repository, passphrase)
    artifact, release = gui_bundle(tmp_path / "builds", 1, "1.0.0")
    pending = prepare_release(publisher, artifact, release)
    approve_release(publisher, pending, 1, passphrase)
    approve_release(publisher, pending, 2, passphrase)
    publish_release(publisher, pending, passphrase)

    with serve_directory(repository) as url:
        launcher = ROOT / "demo_app" / "gui_launcher.py"
        client = tmp_path / "client"
        # --install --status: initialize, install, report state, and exit without running the app.
        completed = subprocess.run(
            [sys.executable, str(launcher), "--client-dir", str(client),
             "--bootstrap", str(bootstrap), "--repository-url", url,
             "--app-id", "csv-inspector", "--install", "--status"],
            capture_output=True, text=True, cwd=ROOT, timeout=120)
        assert completed.returncode == 0, completed.stderr + completed.stdout
        lines = [json.loads(line) for line in completed.stdout.strip().splitlines()]
        install = next(line for line in lines if "install" in line)
        assert install["install"]["installed"] is True
        assert (client / "client.json").exists()
        # A later launcher run without install arguments reports the same state.
        again = subprocess.run(
            [sys.executable, str(launcher), "--client-dir", str(client), "--status"],
            capture_output=True, text=True, cwd=ROOT, timeout=60)
        assert again.returncode == 0, again.stderr + again.stdout
        status = json.loads(again.stdout)
        assert status["status"]["active"]["release"]["verified_updates"]["sequence"] == 1

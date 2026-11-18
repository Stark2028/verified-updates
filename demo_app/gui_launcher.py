"""Thin desktop launcher for the verified CSV Inspector.

The launcher holds no trust material and performs no verification. Every
update, download, integrity check and activation is delegated to the
verified_updates client CLI, which is the only code that can move the
installed version. The GUI itself is ordinary, replaceable application code:
if the launcher or app were tampered with locally, nothing here would make
the updater accept a bad release, because the TUF client owns all of that
state.

Modes:
  - ensure-installed on first run:  --install with --bootstrap and
    --repository-url (the bootstrap is a genuine root obtained out-of-band);
  - run one verified update:        --check-updates;
  - open the desktop viewer:        --gui (passes --client-dir to the app so
    its "Check for updates" button calls the same verified CLI).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str]) -> dict:
    completed = subprocess.run([sys.executable, "-m", "verified_updates"] + args,
                               capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"raw_stdout": completed.stdout, "raw_stderr": completed.stderr}
    payload["exit_code"] = completed.returncode
    return payload


def install_or_update(client_dir: Path, *, bootstrap: Path, repository_url: str,
                      app_id: str, platform: str = "windows-amd64") -> dict:
    """First-time trusted init from a genuine bootstrap, then one update."""
    if not (client_dir / "client.json").exists():
        result = _run_cli(["client", "init", "--client", str(client_dir),
                           "--bootstrap", str(bootstrap),
                           "--repository-url", repository_url,
                           "--app-id", app_id, "--platform", platform])
        if "error" in result:
            return {"installed": False, "reason": result["error"], "detail": result.get("detail", "")}
    return {"installed": update(client_dir)["outcome"] in ("updated", "up_to_date")}


def update(client_dir: Path) -> dict:
    return _run_cli(["client", "update", "--client", str(client_dir)])


def run_headless(client_dir: Path, app_args: list[str]) -> int:
    """Run the installed app through the verified CLI and forward its exit code."""
    result = _run_cli(["client", "run", "--client", str(client_dir), "--"] + app_args)
    return result.get("exit_code", 0)


def open_gui(client_dir: Path, app_args: list[str]) -> int:
    """Open the interactive desktop viewer; its update button uses this same CLI."""
    viewer = Path(__file__).with_name("csv_viewer_gui.py")
    completed = subprocess.run([sys.executable, str(viewer)] + app_args + ["--client-dir", str(client_dir)],
                               text=True, cwd=Path(__file__).resolve().parent.parent)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the verified CSV Inspector and check for updates.")
    parser.add_argument("--client-dir", type=Path, required=True)
    parser.add_argument("--bootstrap", type=Path, help="Genuine bootstrap root for first-time install.")
    parser.add_argument("--repository-url", help="Repository URL for first-time install.")
    parser.add_argument("--app-id", default="csv-inspector")
    parser.add_argument("--platform", default="windows-amd64")
    parser.add_argument("--install", action="store_true",
                        help="Initialize from --bootstrap and install the latest release before running.")
    parser.add_argument("--check-updates", action="store_true", help="Run one verified update before running.")
    parser.add_argument("--status", action="store_true",
                        help="Report the installed state and exit; do not run the app.")
    parser.add_argument("--gui", action="store_true", help="Open the desktop viewer instead of headless output.")
    parser.add_argument("--app-arg", action="append", default=[], dest="app_args",
                        help="Forward a single argument to the CSV Inspector; repeat for each.")
    args = parser.parse_args()

    client_dir = args.client_dir.resolve()
    if args.install or (args.bootstrap and args.repository_url and not (client_dir / "client.json").exists()):
        if not args.bootstrap or not args.repository_url:
            print(json.dumps({"error": "BOOTSTRAP_REQUIRED",
                              "detail": "First-time install needs --bootstrap and --repository-url."}))
            return 2
        print(json.dumps({"install": install_or_update(
            client_dir, bootstrap=args.bootstrap, repository_url=args.repository_url,
            app_id=args.app_id, platform=args.platform)}))
    if args.check_updates:
        print(json.dumps({"update": update(client_dir)}))
    if args.status:
        status = _run_cli(["client", "status", "--client", str(client_dir)])
        print(json.dumps({"status": status}))
        return 0

    if args.gui:
        return open_gui(client_dir, args.app_args)
    return run_headless(client_dir, args.app_args)


if __name__ == "__main__":
    raise SystemExit(main())

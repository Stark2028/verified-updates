"""Explicit CLI for publisher custody, client operations and reproducible labs."""

import argparse
import getpass
import json
import os
from pathlib import Path
from threading import Event

from tuf.api.exceptions import RepositoryError
from tuf.api.serialization import DeserializationError

from verified_updates.client import initialize_client, update
from verified_updates.contracts import Release, UpdateError
from verified_updates.installer import active_state, build_bundle, run_installed
from verified_updates.keys import generate_maintainer_key, load_public_key
from verified_updates.publisher import (
    approve_release, configuration, export_request, import_approval, initialize,
    inspect_release, prepare_release, publish_release, rotate_targets_key,
)
from verified_updates.server import serve_directory


def _passphrase() -> bytes:
    value = os.environ.get("VU_KEY_PASSPHRASE")
    return (value if value is not None else getpass.getpass("Publisher key passphrase: ")).encode("utf-8")


def _release_flags(parser) -> None:
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--platform", default="windows-amd64")
    parser.add_argument("--version", required=True)
    parser.add_argument("--sequence", type=int, required=True)
    parser.add_argument("--entrypoint", default="app.py")


def _release(args) -> Release:
    return Release(args.app_id, args.platform, args.version, args.sequence, args.entrypoint)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="verified-updates", description="TUF-based application updates and attack experiments.")
    commands = root.add_subparsers(dest="command", required=True)
    pub = commands.add_parser("publisher").add_subparsers(dest="action", required=True)
    init = pub.add_parser("init")
    init.add_argument("--publisher", type=Path, required=True)
    init.add_argument("--repository", type=Path, required=True)
    init.add_argument("--maintainer-key", type=Path, action="append", help="Repeat for each of three separate Ed25519 public keys.")
    prepare = pub.add_parser("prepare")
    prepare.add_argument("--publisher", type=Path, required=True)
    prepare.add_argument("--artifact", type=Path, required=True)
    _release_flags(prepare)
    for name in ("inspect", "approve", "publish"):
        command = pub.add_parser(name)
        command.add_argument("--publisher", type=Path, required=True)
        command.add_argument("--release", required=True)
        if name == "approve":
            command.add_argument("--signer", type=int, required=True)
    for name, file_flag in (("export-request", "--output"), ("import-approval", "--approval")):
        command = pub.add_parser(name)
        command.add_argument("--publisher", type=Path, required=True)
        command.add_argument("--release", required=True)
        command.add_argument(file_flag, type=Path, required=True)
    rotate = pub.add_parser("rotate-targets-key")
    rotate.add_argument("--publisher", type=Path, required=True)
    rotate.add_argument("--signer", type=int, required=True)
    info = pub.add_parser("info")
    info.add_argument("--publisher", type=Path, required=True)
    maintainer = commands.add_parser("maintainer").add_subparsers(dest="action", required=True)
    keygen = maintainer.add_parser("keygen")
    keygen.add_argument("--key-dir", type=Path, required=True)
    for action in ("inspect", "sign"):
        command = maintainer.add_parser(action)
        for flag in ("--request", "--artifact", "--root"):
            command.add_argument(flag, type=Path, required=True)
        if action == "sign":
            command.add_argument("--key-dir", type=Path, required=True)
            command.add_argument("--key-id", required=True)
            command.add_argument("--expect-digest", required=True)
            command.add_argument("--output", type=Path, required=True)
    client = commands.add_parser("client").add_subparsers(dest="action", required=True)
    init = client.add_parser("init")
    init.add_argument("--client", type=Path, required=True)
    init.add_argument("--bootstrap", type=Path, required=True)
    init.add_argument("--repository-url", required=True)
    init.add_argument("--app-id", required=True)
    init.add_argument("--platform", default="windows-amd64")
    for name in ("update", "status", "run"):
        command = client.add_parser(name)
        command.add_argument("--client", type=Path, required=True)
        if name == "run":
            command.add_argument("arguments", nargs=argparse.REMAINDER)
    bundle = commands.add_parser("bundle")
    bundle.add_argument("--source", type=Path, required=True)
    bundle.add_argument("--output", type=Path, required=True)
    _release_flags(bundle)
    server = commands.add_parser("serve")
    server.add_argument("--repository", type=Path, required=True)
    server.add_argument("--port", type=int, default=8080)
    demo = commands.add_parser("demo")
    demo.add_argument("--directory", type=Path)
    demo.add_argument("--summary", action="store_true", help="Print concise results and report paths instead of full JSON.")
    report = commands.add_parser("report")
    report.add_argument("--input", type=Path, required=True)
    report.add_argument("--output", type=Path)
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--directory", type=Path)
    benchmark.add_argument("--samples", type=int, default=15)
    benchmark.add_argument("--payload-kib", type=int, default=1024)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "publisher":
            if args.action == "init":
                keys = [load_public_key(path) for path in args.maintainer_key] if args.maintainer_key else None
                result = {"bootstrap": str(initialize(args.publisher, args.repository, _passphrase(), maintainer_keys=keys))}
            elif args.action == "prepare":
                result = {"release_id": prepare_release(args.publisher, args.artifact, _release(args))}
            elif args.action == "inspect":
                result = inspect_release(args.publisher, args.release)
            elif args.action == "approve":
                result = {"signature_count": approve_release(args.publisher, args.release, args.signer, _passphrase())}
            elif args.action == "publish":
                result = {"target_path": publish_release(args.publisher, args.release, _passphrase())}
            elif args.action == "rotate-targets-key":
                result = {"new_keyid": rotate_targets_key(args.publisher, args.signer, _passphrase())}
            elif args.action == "export-request":
                result = {"request": str(export_request(args.publisher, args.release, args.output))}
            elif args.action == "import-approval":
                result = {"signature_count": import_approval(args.publisher, args.release, args.approval)}
            else:
                result = configuration(args.publisher)
        elif args.command == "maintainer":
            from verified_updates.approvals import inspect_request, sign_request

            if args.action == "keygen":
                public = generate_maintainer_key(args.key_dir, _passphrase())
                result = {"public_key": str(public.resolve()), "keyid": load_public_key(public).keyid}
            elif args.action == "inspect":
                result = inspect_request(args.request, args.artifact, args.root)
            else:
                result = sign_request(args.request, args.artifact, args.root, args.key_dir, args.key_id,
                                      _passphrase(), args.expect_digest, args.output)
        elif args.command == "client":
            if args.action == "init":
                initialize_client(args.client, args.bootstrap, args.repository_url, args.app_id, args.platform)
                result = {"initialized": str(args.client.resolve())}
            elif args.action == "update":
                result = update(args.client).to_dict()
                print(json.dumps(result, indent=2))
                return 0 if result["outcome"] in ("updated", "up_to_date") else 3 if result["outcome"] == "rejected" else 4
            elif args.action == "run":
                arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
                return run_installed(args.client.resolve(), arguments)
            else:
                result = {"active": active_state(args.client)}
        elif args.command == "bundle":
            result = {"artifact": str(build_bundle(args.source, args.output, _release(args)))}
        elif args.command == "serve":
            with serve_directory(args.repository, args.port) as url:
                print(json.dumps({"repository_url": url}), flush=True)
                Event().wait()
            return 0
        elif args.command == "report":
            from verified_updates.report import render_report
            output = args.output or args.input.with_suffix(".html")
            if output.resolve() == args.input.resolve():
                raise UpdateError("INVALID_INPUT", "HTML output must differ from the JSON evidence file.")
            render_report(json.loads(args.input.read_text(encoding="utf-8")), output, source=args.input)
            result = {"report": str(output.resolve())}
        elif args.command == "benchmark":
            from verified_updates.benchmark import run_benchmark

            measured = run_benchmark(args.samples, args.payload_kib, args.directory)
            result = {key: value for key, value in measured.items() if key != "samples"}
        else:
            from verified_updates.lab import run_demo
            result = run_demo(args.directory)
            if args.summary:
                for case in result["cases"]:
                    outcome = case["actual"].get("outcome", "interrupted")
                    print(f"{'PASS' if case['passed'] else 'FAIL'}  {case['scenario']}: {outcome}")
                print(f"Comparison cases passed: {sum(row['passed'] for row in result['comparison'])}/{len(result['comparison'])}")
                print(f"HTML report: {Path(result['directory']) / 'report.html'}")
                print(f"JSON evidence: {Path(result['directory']) / 'report.json'}")
            else:
                print(json.dumps(result, indent=2))
            return 0 if result["all_passed"] else 1
        print(json.dumps(result, indent=2))
        return 0
    except (UpdateError, RepositoryError, DeserializationError, OSError, ValueError) as exc:
        print(json.dumps({"error": getattr(exc, "code", type(exc).__name__), "detail": str(exc)}, indent=2))
        return 2
    except KeyboardInterrupt:
        return 130


"""Measure verified v1-to-v2 updates over the real local repository."""

import os
import platform
import secrets
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile

from tuf.ngclient.urllib3_fetcher import Urllib3Fetcher

from verified_updates.client import initialize_client, update
from verified_updates.contracts import UpdateError
from verified_updates.publisher import approve_release, initialize, prepare_release, publish_release
from verified_updates.reference import reference_bundle
from verified_updates.server import serve_directory
from verified_updates.storage import write_json


class CountingFetcher(Urllib3Fetcher):
    def __init__(self):
        super().__init__()
        self.metadata_bytes = 0
        self.artifact_bytes = 0

    def _fetch(self, url):
        is_metadata = urlsplit(url).path.startswith("/metadata/")
        for chunk in super()._fetch(url):
            if is_metadata:
                self.metadata_bytes += len(chunk)
            else:
                self.artifact_bytes += len(chunk)
            yield chunk


def _hardware() -> dict:
    cpu = platform.processor()
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    return {"cpu": cpu or platform.machine(), "logical_cpus": os.cpu_count(), "os": platform.platform(), "python": platform.python_version()}


def run_benchmark(samples: int, payload_kib: int, directory: Path | None = None) -> dict:
    if not 1 <= samples <= 100 or not 1 <= payload_kib <= 60 * 1024:
        raise UpdateError("INVALID_INPUT", "Use 1–100 samples and a payload between 1 KiB and 60 MiB.")
    base = (directory or Path(".runtime") / f"benchmark-{uuid4().hex[:12]}").resolve()
    base.mkdir(parents=True, exist_ok=False)
    publisher, repository = base / "publisher", base / "repository"
    passphrase = secrets.token_urlsafe(32).encode()
    bootstrap = initialize(publisher, repository, passphrase)

    def publish(sequence):
        bundle, release = reference_bundle(base / "builds", sequence, f"1.{sequence - 1}.0")
        if sequence == 2:
            with ZipFile(bundle, "a", compression=ZIP_STORED) as archive:
                archive.writestr("benchmark-data.bin", bytes(payload_kib * 1024))
        pending = prepare_release(publisher, bundle, release)
        for signer in (1, 2):
            approve_release(publisher, pending, signer, passphrase)
        publish_release(publisher, pending, passphrase)
        return bundle.stat().st_size

    previous_no_proxy = os.environ.get("no_proxy")
    os.environ["no_proxy"] = ",".join(filter(None, (previous_no_proxy, "127.0.0.1", "localhost")))
    try:
        with serve_directory(repository) as url:
            publish(1)
            clients = [base / "clients" / str(index) for index in range(samples + 1)]
            for client in clients:
                initialize_client(client, bootstrap, url, "csv-inspector", "windows-amd64")
                result = update(client)
                if result.installed_after != 1:
                    raise UpdateError("BENCHMARK_FAILED", result.detail)
            bundle_bytes = publish(2)
            runs = []
            for client in clients:
                fetcher, timings = CountingFetcher(), {}
                result = update(client, timings=timings, fetcher=fetcher)
                if result.outcome != "updated" or result.installed_after != 2 or fetcher.artifact_bytes != bundle_bytes:
                    raise UpdateError("BENCHMARK_FAILED", result.detail)
                runs.append({**timings, "metadata_bytes": fetcher.metadata_bytes, "artifact_bytes": fetcher.artifact_bytes})
    finally:
        if previous_no_proxy is None:
            del os.environ["no_proxy"]
        else:
            os.environ["no_proxy"] = previous_no_proxy
    measured = runs[1:]
    report = {
        "schema_version": 1, "environment": _hardware(), "bundle_bytes": bundle_bytes,
        "warmup_runs_excluded": 1, "sample_count": samples, "samples": measured,
        "median": {field: round(median(run[field] for run in measured), 3) for field in measured[0]},
        "method": "Loopback HTTP, preinstalled v1, sequential v2 updates. Metadata and artifact timings include verification inside python-tuf. Byte counts cover response bodies consumed by the verifier.",
    }
    path = base / "benchmark.json"
    write_json(path, report)
    return {"report": str(path), **report}

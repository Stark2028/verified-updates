"""Build distinct real reference-app versions for the local demonstration."""

from pathlib import Path

from demo_app import csv_inspector
from verified_updates.contracts import Release
from verified_updates.installer import build_bundle


def reference_bundle(directory: Path, sequence: int, version: str, *, broken: bool = False) -> tuple[Path, Release]:
    directory.mkdir(parents=True, exist_ok=True)
    source = Path(csv_inspector.__file__).read_text(encoding="utf-8")
    source = source.replace('APP_VERSION = "1.0.0"', f"APP_VERSION = {version!r}")
    if sequence >= 2:
        source = source.replace("FEATURE_SUMMARIES = False", "FEATURE_SUMMARIES = True")
    if broken:
        source = "raise SystemExit(17)\n" + source
    generated = directory / f"csv_inspector_{sequence}.py"
    generated.write_text(source, encoding="utf-8")
    release = Release("csv-inspector", "windows-amd64", version, sequence)
    return build_bundle(generated, directory / f"csv-inspector-{sequence}.zip", release), release


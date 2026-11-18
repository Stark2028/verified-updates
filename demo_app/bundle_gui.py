"""Build GUI CSV Inspector releases as signed ZIP bundles.

Mirrors demo_app/reference.py: sequence 1 ships the base viewer, sequences
2 and later enable numeric summaries so a genuine update has a visible new
feature. ``broken=True`` makes the self-test fail so the installer keeps the
previous version. The installer verifies and self-tests before activation, so
a broken authorized release never becomes active.
"""

import shutil
import tempfile
from pathlib import Path

from demo_app import csv_viewer_gui
from verified_updates.contracts import Release
from verified_updates.installer import build_bundle


def gui_bundle(directory: Path, sequence: int, version: str, *, broken: bool = False) -> tuple[Path, Release]:
    """Copy the GUI source, patch its version/feature flags, and bundle it."""
    directory.mkdir(parents=True, exist_ok=True)
    source = Path(csv_viewer_gui.__file__).read_text(encoding="utf-8")
    source = source.replace('APP_VERSION = "1.0.0"', f"APP_VERSION = {version!r}")
    if sequence >= 2:
        source = source.replace("FEATURE_SUMMARIES = False", "FEATURE_SUMMARIES = True")
    if broken:
        # Keep the app importable so only its pre-activation self-test fails.
        source = source.replace(
            "def self_test() -> int:\n",
            "def self_test() -> int:\n    if True:\n        return 17\n",
        )
    with tempfile.TemporaryDirectory() as scratch:
        generated = Path(scratch) / f"csv_viewer_{sequence}.py"
        generated.write_text(source, encoding="utf-8")
        # Copy into the output tree so the source file persists with the build.
        generated_out = directory / f"csv_viewer_{sequence}.py"
        shutil.copyfile(generated, generated_out)
    release = Release("csv-inspector", "windows-amd64", version, sequence, entrypoint="app.py")
    return build_bundle(generated_out, directory / f"csv-inspector-{sequence}.zip", release), release

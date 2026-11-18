# Desktop CSV Inspector

`demo_app/csv_viewer_gui.py` is the Tkinter reference application: open a CSV, filter rows, export the filtered result, and (from the second release on) see numeric summaries. `demo_app/bundle_gui.py` builds its signed ZIP releases — sequence 1 ships the base viewer, sequence 2 adds summaries, so a genuine update has a visible new feature.

## Trust boundary

The GUI app and its launcher (`demo_app/gui_launcher.py`) contain **no trust material and no verification logic**. The launcher is deliberately thin: it initializes the client from a genuine bootstrap, runs `verified_updates client update`, and launches the installed version through the same CLI. The in-app "Check for updates" button calls the updater CLI too. All TUF verification, integrity checks, staging and activation stay in the verified updater; the desktop layer cannot bypass or weaken them. If the app files are tampered with locally, that is outside the repository-compromise model — the updater still only accepts authorized releases.

## First-time install and run

Prepare a GUI release with the publisher workflow in the README, then use `bundle_gui` to build the artifact instead of the CLI source bundle:

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python -m verified_updates client init --client .runtime/gui/client --bootstrap .runtime/manual/publisher/bootstrap/root.json --repository-url http://127.0.0.1:8080/ --app-id csv-inspector
& $python -m verified_updates gui-launcher --client-dir .runtime/gui/client --install --status
```

`--install` initializes from the bootstrap when no client exists yet and runs one verified update; `--status` reports the installed state and exits. To open the interactive viewer:

```powershell
& $python -m verified_updates gui-launcher --client-dir .runtime/gui/client --gui
```

The toolbar's **Check for updates** button performs the same verified update and reports the outcome. After an update, restart the app (`--gui` again) to run the new version.

## Headless use

The app mirrors the CLI Inspector for non-interactive work and self-tests:

```powershell
& $python -m verified_updates client run --client .runtime/gui/client -- demo_app/sample.csv --contains Engineering
```

The generated app files also accept `--version`, `--self-test`, and `file --contains --export` without a display.

## Presentation

Publish two releases with `demo_app/bundle_gui.py` (sequence 1, then sequence 2 with `FEATURE_SUMMARIES` enabled). Install the first, open the app, then **Check for updates** and restart: the second version shows the numeric-summaries panel on the same CSV. A tampered second release is rejected and the working version is retained, exactly as the CLI lab demonstrates.

## Tests

`tests/test_launcher.py` runs the GUI bundles through the real TUF pipeline (install, update, restart, tampered-release rejection) in fresh processes, verifies the headless CLI paths, builds a broken release and confirms its pre-commit self-test fails, and checks the launcher only routes work through the verified CLI. The widget self-test runs on hosts with a display.

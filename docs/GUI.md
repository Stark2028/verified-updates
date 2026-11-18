# Desktop CSV Inspector

`demo_app/csv_viewer_gui.py` is the Tkinter reference application: open a CSV, filter rows, export the filtered result, and (from the second release on) see numeric summaries. `demo_app/bundle_gui.py` builds its signed ZIP releases — sequence 1 ships the base viewer, sequence 2 adds summaries, so a genuine update has a visible new feature.

## Trust boundary

The GUI app and its launcher (`demo_app/gui_launcher.py`) contain **no trust material and no verification logic**. The launcher is deliberately thin: it initializes the client from a genuine bootstrap, runs `verified_updates client update`, and launches the installed version through the same CLI. The in-app "Check for updates" button calls the updater CLI too. All TUF verification, integrity checks, staging and activation stay in the verified updater; the desktop layer cannot bypass or weaken them. If the app files are tampered with locally, that is outside the repository-compromise model — the updater still only accepts authorized releases.

## Run the complete desktop workflow

From the project directory, with the README environment installed, run:

```powershell
.\.venv\Scripts\python.exe -m verified_updates desktop-demo --show
```

Each run creates a fresh publisher, repository and client. The PowerShell window announces each stage.

1. Show **1.0.0** in the title bar and the sample CSV. Click **Check for updates**. The bottom status line shows `TARGET_INTEGRITY_FAILED` and the title remains at v1. Close the window after showing the result.
2. The demo restores the genuine bundle and opens v1 again. Click **Check for updates** and show the successful update to **1.1.0**. Close to open the newly installed release.
3. Show **1.1.0** in the title bar and the **Numeric summaries** panel for the same CSV. This is the new feature in v2.

Closing either v1 window before checking stops the demo with an instruction to retry. Omit `--show` for unattended verification. The lab repository is available while the command is running.

## Control the release during a live walkthrough

```powershell
.\.venv\Scripts\python.exe -m verified_updates desktop-demo --operator
```

The prompt starts with v1 installed and waits for your commands. The release keys are separate identities held by the local demo publisher. The [detached approval workflow](APPROVALS.md) can demonstrate custody on separate machines.

| Enter at `updates>` | What to show |
| --- | --- |
| `prepare`, `approve 1`, `publish` | Show the draft's SHA-256 digest and the publication refusal with one approval. Repeat `approve 1` if you want to show that it still counts once. |
| `approve 2`, `publish` | Two authorized signatures allow publication. |
| `change`, `open` | Click **Check for updates** in the v1 app. Explain the hash mismatch and show that v1 stays active. Close the app to return to the prompt. |
| `restore`, `open`, `open` | In the first window, click **Check for updates** and close after the successful update. Open again to see v2's numeric summaries. |
| `replay`, `check` | Show `METADATA_ROLLBACK`. The original v1 metadata has a valid signature. The client remembers seeing newer metadata. |
| `restore`, `status`, `exit` | Restore the repository and confirm v2 is still active. |

Use `check` whenever you want the updater's exact diagnostic in PowerShell. The prompt remains open until you exit, so you can pause at each decision and answer questions.

## First-time install from your own repository

Build the GUI ZIP with `demo_app.bundle_gui.gui_bundle`, publish it with the README publisher workflow, then serve the public repository. Install the published release and inspect the client state:

```powershell
$python = '.\.venv\Scripts\python.exe'
$env:NO_PROXY = "$env:NO_PROXY,127.0.0.1,localhost"
& $python -m verified_updates gui-launcher --client-dir .runtime/gui/client --bootstrap .runtime/manual/publisher/bootstrap/root.json --repository-url http://127.0.0.1:8080/ --install --status
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

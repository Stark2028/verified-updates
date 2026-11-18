# Shared implementation handoff

Last updated: 2026-11-19 (Asia/Calcutta).

## End-to-end desktop and renewal checkpoint

- The user scoped this pass to the working project. Course reports and slides are excluded.
- `python -m verified_updates gui-launcher` now opens the active installed app through `client run`. Both headless and desktop paths report the installed version. Verification failures keep their exit codes and do not fall back to a checkout viewer.
- `python -m verified_updates desktop-demo --show` creates a fresh local publisher, repository and client, then opens v1, confirms v1 still opens after rejecting a changed v2 ZIP, and opens genuine v2 with numeric summaries. Close each window to advance. Omit `--show` for the automated launcher checks.
- `publisher renew-metadata --publisher PATH` reissues snapshot and timestamp, while `publisher prepare-renewal --publisher PATH --artifact ORIGINAL_ZIP --app-id csv-inspector` drafts targets renewal for the same release. The targets draft needs two normal or detached approvals. No app release sequence changes.
- `.\.venv\Scripts\python.exe -m pytest -q` passed **48 tests in 58.48s**. The existing HTTP demo passed **11 scenarios and 3 comparisons** in `.runtime/desktop-full-lab/`. The new desktop demo passed in `.runtime/desktop-acceptance/`.
- Built and installed the package into a fresh Windows virtual environment with `pip install -r requirements.lock` and `pip install --no-deps .`. From `.runtime/`, it passed `python -m verified_updates desktop-demo --directory installed-package-acceptance`. Verified import from the fresh environment’s `site-packages`, Tk 8.6.15, and `gui-launcher --client-dir installed-package-acceptance/client --gui --app-arg=--self-test` returned version 1.1.0 and `self_test: passed`. Used the same Windows machine with a fresh Python environment. The visible click-through mode remains available for a manual rehearsal.
- Optional scope includes standalone executable packaging, the operator console, and root or externally held signing key rotation. Python 3.12 and Tkinter remain runtime requirements.

## Independent security review checkpoint

- Reviewed the current core (`client.py`, `publisher.py` incl. the recovery journal, `storage.py`, `keys.py`, `installer.py`, `approvals.py`) against the threat model, not just the original author's assumptions. **No new security defect was found.** The recovery journal replays already-signed bytes without re-signing, fails closed, and is bounded; archive unpacking still rejects traversal/links/reserved names/case-conflict; `import_approval` validates the strict `{keyid, sig}` shape, authorizes against the authoritative root, verifies cryptographically, and dedupes by keyid; the client short-circuits the exact current release without re-verifying the served artifact (correct, since the signed digest already matched).
- Added `tests/test_security_invariants.py` (7 tests) pinning previously-implied invariants: application-sequence rollback (`RELEASE_ROLLBACK`), sequence reuse with a new digest (`RELEASE_SEQUENCE_REUSED`), fail-closed on out-of-schema active state and on an active pointer escaping the version tree, and bootstrap rejection of a root with an under-quorum signature, a non-root role, and garbage bytes. These manipulate trusted operator-side state on purpose: they prove the client fails closed rather than accepting.
- Confirmed documented limits still hold (now also covered by test): a failed post-publication self-test advances `ordering.json` while `active.json` retains the working version; first-time-init and power-loss recovery remain outside the tested interruption cases.
- `.\.venv\Scripts\python.exe -m pytest -q`: **46 passed in 57.05s**.
- Open after this checkpoint: live operator console, final course report + 10–15 minute demo script, root-signer/external-key rotation, metadata renewal, and executable packaging.

## Desktop launcher checkpoint

- `demo_app/csv_viewer_gui.py`: Tkinter CSV Inspector (open, filter, export; numeric summaries enabled by `demo_app/bundle_gui.py` from sequence 2). CLI-compatible headless paths: `--version`, `--self-test`, `file --contains --export`. The `--self-test` constructs the Tk widgets, so it works on a desktop and stays portable on headless hosts.
- `demo_app/bundle_gui.py`: builds GUI releases into signed ZIPs with `entrypoint=app.py`, mirroring `reference.py` (summaries from sequence 2; `broken=True` makes only the pre-commit self-test fail with exit 17).
- `demo_app/gui_launcher.py`: thin launcher with zero trust material and zero verification. `--install` initializes from a genuine bootstrap then updates; `--check-updates` runs the verified updater CLI; `--gui` opens the app with `--client-dir` so its in-app "Check for updates" button calls the same CLI; `--status` reports the installed state. The launcher never bypasses the TUF client.
- `tests/test_launcher.py` (6 tests): GUI bundles through the real TUF pipeline — install seq1, publish seq2, update, restart into 1.1.0 with summaries visible; a tampered seq2 artifact is rejected with `TARGET_INTEGRITY_FAILED` while the working version is retained; broken release fails its self-test; headless CLI paths; launcher delegation. The widget test passes on this host (display available) and is skipped headless.
- `docs/GUI.md` documents the trust boundary, first-time install, update/restart, and the presentation sequence.
- `.\.venv\Scripts\python.exe -m pytest -q`: **39 passed in 52.00s**. `pip check` clean. Fresh full demo at `.runtime/demo-761d96b3818d/` passed all 11 scenarios and 3 comparisons.
- Limits: GUI releases remain source ZIPs run by the local Python interpreter (no PyInstaller standalone executable); the app cannot self-update the launcher; the launcher assumes the package is importable from the venv it is launched from.
- Open after this checkpoint: live operator console, final course report + 10–15 minute demo script, independent security review with regression tests, root-signer/external-key rotation, metadata renewal, and executable packaging.

## Publisher recovery checkpoint

- Release publication and local targets-key rotation now write a private `publication-journal.json` before changing public metadata. The journal contains the exact signed metadata and the pending release or rotation details. The same publisher lock protects normal publication and recovery.
- Run `.\.venv\Scripts\python.exe -m verified_updates publisher recover --publisher PATH` after a process interruption. Recovery checks the staged artifact and replays the original publication without the signing passphrases. Normal release operations pause until recovery succeeds. A second recovery returns `recovered: false`.
- `tests/test_publisher_recovery.py` interrupts a real publisher process before timestamp publication, after timestamp publication, and during local targets-key rotation. It checks the HTTP client's visible release and that publishing can continue afterward.
- Windows atomic writes retry brief sharing conflicts. A persistent failure still surfaces and leaves the journal available for recovery. The lab restores its single changed fixture byte in place between clients, which resolved an observed Windows rename denial during the CLI demo.
- `.\.venv\Scripts\python.exe -m pytest -q` passed 33 tests in 42.71s. The final CLI demo passed 11 scenarios and 3 comparisons with `.\.venv\Scripts\python.exe -m verified_updates demo --directory .runtime/publisher-recovery-evidence --summary`. The HTML and JSON in that directory are the latest full demo evidence. Omit the directory flag to create a fresh run.
- Recovery assumes intact private staging and journal files. First-time initialization, power loss, expired metadata renewal and rotation of externally held keys remain open. Claude's separate desktop launcher plan continues to use the existing ZIP format and client interfaces.

## Git, performance and detached approvals checkpoint

- The project is a local Git repository on `main`. The baseline commit is `48e90e3`. Git and package authorship are set to Sameer. The local Git email uses the no-reply address for `Stark2028`. Runtime files, caches, the virtual environment and PEM files stay outside Git tracking.
- `python -m verified_updates benchmark --samples 15 --payload-kib 1024` measured a 203.0 ms median update and 1,803 metadata bytes for a 1,050,391-byte bundle. The report gives the methodology and limitations. All samples are kept in `docs/evidence/benchmark-windows-1mib.json`. See `docs/MEASUREMENTS.md`.
- External targets approval is available through `publisher init --maintainer-key`, `publisher export-request`, `maintainer inspect`, `maintainer sign`, and `publisher import-approval`. Three public keys are enrolled. Two private keys in separate directories with distinct passphrases approved an artifact that the official updater then installed over HTTP. A wrong artifact, an altered request digest and an approval for another release were rejected. Reimporting a signature did not increase the count. This was tested on one machine. See `docs/APPROVALS.md`.
- `.\.venv\Scripts\python.exe -m pytest -q` passed 30 tests in 35.29s. A separate CLI smoke run generated keys, inspected and signed a request, imported each approval, and confirmed that publication fails with one and succeeds with two. `pip check` found no broken requirements.
- The existing 11-case demo and three comparisons still pass. The latest full demo is `.runtime/review-detached-baseline/report.html`, generated with `.\.venv\Scripts\python.exe -m verified_updates demo --directory .runtime/review-detached-baseline --summary`. Omit the directory flag for a fresh run.
- Next presentation work is the desktop launcher and a 10–15 minute script. The measurements and approval guide are ready to cite in the report. The newer checkpoint above covers publisher crash recovery.

## Review checkpoint

The November 19 review reran the existing suite (24 passed), then fixed issues in bootstrap provisioning, publisher approvals, report export links, and CSV parsing. The expanded suite passed **29 tests in 34.76s**. Dependency consistency and Python compilation passed. A new run at `.runtime/review-2026-11-19/` passed all **11 scenarios and 3 comparisons**. Its HTML and JSON are the latest evidence. The original milestone remains available for comparison.

Review commands were `.\.venv\Scripts\python.exe -m pytest -q`, `.\.venv\Scripts\python.exe -m pip check`, and `.\.venv\Scripts\python.exe -m verified_updates demo --directory .runtime/review-2026-11-19 --summary`. `node scripts/check-report.mjs .runtime/review-2026-11-19/report.html` confirmed layout width, disclosures and keyboard focus at 1440px and 390px. The installed app also filtered the sample CSV to two Engineering rows with a mean of 87.5.

- Client initialization now validates the supplied root and its self-signature quorum before creating client state. Operators still obtain that root through a trusted distribution channel.
- `publisher inspect --publisher PATH --release ID` reports the exact release, artifact size and SHA-256 digest, and verified signer count. Inspect and approve both reject stale drafts, expired metadata, and altered staged artifacts. Publishing writes the same bytes whose digest it checked.
- The demo records the real publisher inspection result in the first successful installation and the one-signer rejection. The mix-and-match fixture now serves an actual older snapshot in place of the newer one.
- Report exports link back to the selected evidence file. CSV errors are reported cleanly, non-finite numeric columns are excluded from statistics, and the export cannot overwrite its source file.

At this earlier review, publisher recovery, metadata renewal and approval exchange were open. The checkpoint above records the subsequent approval work. The local HTTP server and source-bundle installer remain scoped to the current demo. There has been no production deployment, independent security audit, or external vulnerability database scan.

## User intent and decisions

- Build a substantial, demonstrable cryptography project; time is not the deciding constraint.
- The selected direction is **Secure Software Updates Under Repository Compromise**, based on TUF.
- User explicitly requested deleting the old files. `ITC_PROJECT/` and the separate `rea/` checkout were removed. `PROJECT_BLUEPRINT.md` was retained.
- Implement at the workspace root, rather than the sibling directory proposed in the original blueprint.
- Claude will help or continue when Codex credits run out. Read this file and CLAUDE.md instead of relying on chat history.

## Current implementation status

Milestone 1 is implemented and verified: a real publisher -> HTTP repository -> TUF client -> installed Python application workflow, adversarial scenarios, comparison clients, and an offline evidence report. This is a working initial implementation, not the full target product or a production-readiness claim.

The local `.venv` is provisioned. Runtime dependencies are pinned in pyproject.toml; requirements.lock records the full installed/tested environment. Python 3.12.10, tuf 7.0.1, securesystemslib 1.6.0, cryptography 50.0.2, pytest 9.2.0.

Implemented:

- Encrypted PKCS8 Ed25519 publisher keys outside the served tree.
- Separate root/targets/snapshot/timestamp roles; root and targets use two distinct signatures out of three.
- Prepare -> approve -> publish CLI operations, duplicate-signer rejection, stale-approval rejection.
- Private authoritative publisher state: preparing a release never trusts public repository metadata.
- Hash-prefixed artifacts, versioned metadata, timestamp published last.
- Authentic initial bootstrap root and persistent official python-tuf client metadata.
- Signed application/platform identity, explicit schema and monotonic application sequence/digest policy.
- Actual ZIP downloads, pre-execution authenticity/integrity verification, bounded extraction, original ZIP-name validation, manifest agreement, self-test, atomic active pointer, retained older versions.
- Targets-signer replacement authorized by a root update. Root-signing keys themselves are NOT rotated by the current CLI.
- Structured success/rejection/operational errors, including unreachable-repository transport errors, and per-run JSON event files.
- A useful CLI CSV Inspector: read CSV, filter rows, export, and numeric summaries in subsequent demo releases.
- A real HTTP lab using a new client process per update, plus an actual os._exit(73) test immediately before the activation commit and recovery in a fresh process.
- Local-only unsigned-checksum and signature-only acceptance baselines; comparison results link to actual TUF run IDs.
- An offline HTML report with actual JSON disclosures, comparison table, captured installed-app output, explicit boundaries, and escaped untrusted diagnostics.
- README, docs/ARCHITECTURE.md, docs/THREAT_MODEL.md, docs/DEMO.md, PRODUCT.md and DESIGN.md.

Packaged executable, desktop GUI, live management console, and root-signer rotation remain open.

## Verified commands and evidence

Run from C:\Users\Sameer\Desktop\crptography in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m verified_updates demo --summary
.\.venv\Scripts\python.exe -m pip check
```

- Original milestone test suite: **24 passed in 33.03s**, exit 0. See the review checkpoint above for the current run.
- `pip check`: no broken requirements.
- Recorded milestone command: `.\.venv\Scripts\python.exe -m verified_updates demo --directory .runtime/milestone-1 --summary`, exit 0.
- Milestone evidence: `.runtime/milestone-1/report.json` and `.runtime/milestone-1/report.html`.
- **11/11 scenarios** matched expected results; **3/3 comparison cases** matched expected acceptance decisions.
- Final installed app is display version 1.3.0 / sequence 4, despite rejected/failed sequence-5 activation; sample CSV output contains 4 records and mean score 89.5.
- Do NOT rerun with the same explicit milestone directory; the demo deliberately refuses to overwrite evidence. Omit --directory for a fresh random run.

Report browser verification:

```powershell
node scripts/check-report.mjs .runtime/milestone-1/report.html
```

The actually captured/reviewed run was `.runtime/demo-d614a59d36ea/report.html`, produced by the same current renderer and scenario implementation. Desktop 1440x1000 and mobile 390x844 passed page-overflow, disclosure and keyboard-focus checks; screenshots and browser-checks.json are in `.impeccable/review/`. A fresh finish reviewer returned SHIP with no material defects within that report/capture scope. It did not independently rerun cryptographic experiments. The optional Impeccable engine could not load due to its external cache being unavailable; no engine detector result is claimed.

The original model/earlier source may mention a prototype folder: the new package is `verified_updates/` directly at the root, NOT a nested verified-updates/src directory.

## Environment observations

- Codex sandbox blocked Python's default temporary files and some atomic ZIP operations. Dependency provisioning, real integration tests and demos were run with the tool's approved escalation. This is execution-environment behaviour; normal local PowerShell does not need that tool flag.
- The escalated command environment routed loopback through a proxy even though the sandbox environment did not. Lab subprocesses explicitly add only 127.0.0.1/localhost to NO_PROXY; normal remote-client proxy behaviour is preserved. Manual localhost usage has the corresponding README command.
- Initial failed demo directories are retained under .runtime/ as evidence; the milestone-1 report is the successful checkpoint.
- Old nested repositories were removed with their old projects at the user's request. The project now uses one local repository at the workspace root.
- No ongoing repository HTTP server is needed to view the completed HTML report or run the installed application.

## Core requirements

- Official TUF metadata and client verification, authentic bootstrap root, persisted client trust.
- Separate publisher keys and served repository; encrypted private keys.
- Two-of-three signatures for root and release authorization, separate role keys.
- Actual downloaded application artifacts, safe staging, atomic activation, recovery.
- Repeatable artifact-substitution, rollback, expiry, quorum, and rotation demonstrations.
- A real reference application and evidence-based presentation console after the core works.

## Important implementation limits and review targets

1. **Custody:** the default demo keeps keys in one directory. Detached release approvals support isolated key directories and can be exchanged between machines. Root, snapshot and timestamp keys are still grouped at the publisher.
2. **Publisher recovery:** an interrupted release or local targets-key replacement can be replayed from the private journal. Interrupted first-time initialization and power-loss durability remain outside the verified cases.
3. **Installer format:** source ZIP + Python interpreter only. No standalone Windows executable, updater self-update, automatic cleanup, disk-full coverage, power-loss guarantee, or complete interruption matrix. Existing process-crash proof covers the commit boundary only.
4. **Bootstrap/client state:** initial root and client host/state/clock are trusted assumptions. Initial client configuration validation and corrupted-local-state diagnostics can be strengthened. Never fetch an initial key from an untrusted repository and call it authenticated.
5. **Key lifecycle:** the local demo supports targets-key replacement. External targets rotation, root-signer rotation, and metadata renewal remain open.
6. **Academic evaluation:** the baselines, scenario evidence and first measured benchmark are available. The course report and presentation remain open.
7. **UI:** current report is an offline reader. The planned live operator console, desktop application, and published deployment are not implemented.
8. **Independent review:** Claude should review security boundaries and add independent tests; current core/tests were authored by Codex. The report-only finish review is not a security audit.

## Next concrete implementation sequence

1. Run the documented tests and a fresh demo. Read the successful JSON evidence and source before changing contracts.
2. Perform an independent security review of client/publisher state, approvals, archive handling and key rotation. Add regression tests for concrete discovered issues.
3. Review publisher initialization recovery and metadata renewal. Preserve the distinct root and release roles.
4. Package the reference app and launcher for Windows, then adapt the installer to that explicit bundle format while retaining trusted state outside version payloads. Add the GUI CSV viewer and a real update/restart action.
5. Build the local operator console on actual existing result contracts. Keep signing keys outside that process; use the offline report's evidence semantics and design tokens as appropriate.
6. Complete transport and key-lifecycle coverage, and use the recorded benchmark to finish the report and viva script.

## Suggested Claude continuation prompt

> Read AGENTS.md, CLAUDE.md, HANDOFF.md and PROJECT_BLUEPRINT.md. Milestone 1 works; do not restart it or replace TUF verification. Run the documented tests and a fresh demo, then independently review the publisher/client security boundaries and implement the next concrete milestone. Keep source-bundle limitations and single-machine signing custody explicit. Preserve real evidence, use separate file ownership if Codex is active, and update HANDOFF.md with exact results before ending.

## Continuation discipline

Keep this file current after each meaningful milestone. Include exact commands, test counts, observed failures, implementation limits, and specific next steps. Do not silently convert a planned feature into a completed claim.


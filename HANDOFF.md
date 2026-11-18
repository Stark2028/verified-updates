# Shared implementation handoff

Last updated: 2026-11-19 (Asia/Calcutta).

## Review checkpoint

The November 19 review reran the existing suite (24 passed), then fixed issues in bootstrap provisioning, publisher approvals, report export links, and CSV parsing. The expanded suite passed **29 tests in 34.76s**. Dependency consistency and Python compilation passed. A new run at `.runtime/review-2026-11-19/` passed all **11 scenarios and 3 comparisons**. Its HTML and JSON are the latest evidence. The original milestone remains available for comparison.

Review commands were `.\.venv\Scripts\python.exe -m pytest -q`, `.\.venv\Scripts\python.exe -m pip check`, and `.\.venv\Scripts\python.exe -m verified_updates demo --directory .runtime/review-2026-11-19 --summary`. `node scripts/check-report.mjs .runtime/review-2026-11-19/report.html` confirmed layout width, disclosures and keyboard focus at 1440px and 390px. The installed app also filtered the sample CSV to two Engineering rows with a mean of 87.5.

- Client initialization now validates the supplied root and its self-signature quorum before creating client state. Operators still obtain that root through a trusted distribution channel.
- `publisher inspect --publisher PATH --release ID` reports the exact release, artifact size and SHA-256 digest, and verified signer count. Inspect and approve both reject stale drafts, expired metadata, and altered staged artifacts. Publishing writes the same bytes whose digest it checked.
- The demo records the real publisher inspection result in the first successful installation and the one-signer rejection. The mix-and-match fixture now serves an actual older snapshot in place of the newer one.
- Report exports link back to the selected evidence file. CSV errors are reported cleanly, non-finite numeric columns are excluded from statistics, and the export cannot overwrite its source file.

The highest-value remaining engineering work is publisher recovery after interrupted publication or rotation, metadata renewal without a new application release, and approval exchange between maintainers with separate keys. The first two improve ordinary operation. The third makes the two-signature demonstration more meaningful. The local HTTP server and source-bundle installer remain scoped to the current demo. There has been no production deployment, independent security audit, or external vulnerability database scan.

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

No packaged executable, desktop GUI, live management console, independent offline approval exchange, or root-signer rotation CLI exists yet.

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
- No Git repository has been initialized and no commits/pushes were made. Old nested repositories were removed with their old projects at the user's request.
- No ongoing repository HTTP server is needed to view the completed HTML report or run the installed application.

## Core requirements

- Official TUF metadata and client verification, authentic bootstrap root, persisted client trust.
- Separate publisher keys and served repository; encrypted private keys.
- Two-of-three signatures for root and release authorization, separate role keys.
- Actual downloaded application artifacts, safe staging, atomic activation, recovery.
- Repeatable artifact-substitution, rollback, expiry, quorum, and rotation demonstrations.
- A real reference application and evidence-based presentation console after the core works.

## Important implementation limits and review targets

1. **Custody:** approval operations are separate, but all key files are currently in one publisher directory and share a passphrase. Real independent maintainers need portable signing requests, isolated key paths/devices, and signature import/verification. Never present current storage as independent custody.
2. **Publisher recovery:** publication/targets-key replacement updates multiple files; publication ordering is fail-closed for clients, but there is no transactional publisher recovery journal. Review interrupted initialization/publication/rotation before claiming reliable ongoing publisher operation.
3. **Installer format:** source ZIP + Python interpreter only. No standalone Windows executable, updater self-update, automatic cleanup, disk-full coverage, power-loss guarantee, or complete interruption matrix. Existing process-crash proof covers the commit boundary only.
4. **Bootstrap/client state:** initial root and client host/state/clock are trusted assumptions. Initial client configuration validation and corrupted-local-state diagnostics can be strengthened. Never fetch an initial key from an untrusted repository and call it authenticated.
5. **Key lifecycle:** targets-key replacement exists; actual root-signing-key rotation, expired-role maintenance commands and offline approval exchange remain pending.
6. **Academic evaluation:** the three baselines and scenario evidence exist; controlled performance/overhead measurements on recorded hardware and a final course report/presentation are still missing. No real-world attack-detection rate is justified.
7. **UI:** current report is an offline reader. The planned live operator console, desktop application, and published deployment are not implemented.
8. **Independent review:** Claude should review security boundaries and add independent tests; current core/tests were authored by Codex. The report-only finish review is not a security audit.

## Next concrete implementation sequence

1. Run the documented tests and a fresh demo. Read the successful JSON evidence and source before changing contracts.
2. Perform an independent security review of client/publisher state, approvals, archive handling and key rotation. Add regression tests for concrete discovered issues.
3. Add portable approval-request export/sign/import, and strengthen publisher initialization/publication/rotation recovery. Preserve the distinct root and release roles.
4. Package the reference app and launcher for Windows, then adapt the installer to that explicit bundle format while retaining trusted state outside version payloads. Add the GUI CSV viewer and a real update/restart action.
5. Build the local operator console on actual existing result contracts. Keep signing keys outside that process; use the offline report's evidence semantics and design tokens as appropriate.
6. Complete transport/failure coverage and key-lifecycle scenarios, collect real performance measurements, and finish the report/viva/demo script.

## Suggested Claude continuation prompt

> Read AGENTS.md, CLAUDE.md, HANDOFF.md and PROJECT_BLUEPRINT.md. Milestone 1 works; do not restart it or replace TUF verification. Run the documented tests and a fresh demo, then independently review the publisher/client security boundaries and implement the next concrete milestone. Keep source-bundle limitations and single-machine signing custody explicit. Preserve real evidence, use separate file ownership if Codex is active, and update HANDOFF.md with exact results before ending.

## Continuation discipline

Keep this file current after each meaningful milestone. Include exact commands, test counts, observed failures, implementation limits, and specific next steps. Do not silently convert a planned feature into a completed claim.


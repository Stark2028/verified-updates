# Verified Updates

**Secure Software Updates Under Repository Compromise** — a BTech seventh-semester cryptography project.

Author **Sameer** ([Stark2028](https://github.com/Stark2028)).

Publish a real application release, verify it with The Update Framework (TUF), and install it without overwriting the working version. Then alter the repository and observe exactly what the client accepts or rejects.

The current milestone includes a reusable Python updater, a publisher CLI, a working CSV Inspector reference application, a real HTTP attack lab, and an offline HTML evidence report. Windows portable executable packaging and the live management interface remain future milestones.

## Run the demonstration

From this directory in PowerShell, using Python 3.12+:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m verified_updates demo --summary
```

An existing environment in this workspace is already provisioned. Use only the final command to run another experiment.

Each run creates a fresh `.runtime/demo-.../` directory containing:

- `report.html`: offline evidence viewer, with expandable actual client results.
- `report.json`: machine-readable results and comparison decisions.
- `repository/`: public files served during the experiment.
- `publisher/`: encrypted disposable signing keys and private authoritative publication state.
- `clients/`: persisted client trust, actual installed versions, and individual JSON events.
- `builds/`: the actual application release artifacts.

Open the printed `report.html` path in a browser. Reports use no remote fonts, scripts, or services. The lab server closes when the run finishes; the report and installed application remain available.

The demo uses an unrecorded random key passphrase and disposable identities. To operate a persistent repository, use the manual workflow below with your own passphrase. The lab automatically routes its loopback requests directly rather than through an environment proxy.

## Demonstrated behaviour

The current demo records 11 scenarios: initial installation, artifact substitution, recovery with a genuine update, metadata rollback across process restarts, signed expired metadata, insufficient release signatures, inconsistent snapshot metadata, authorized release-key rotation, process interruption immediately before activation, recovery after interruption, and application self-test failure.

The comparison measures artifact acceptance by an unsigned-checksum client, a signature-only client without a replay policy, and the full TUF client. The first accepts an attacker-replaced checksum; the second still accepts a previously signed old release. The main client's actual run IDs connect the comparison to its recorded outcomes. Comparison clients never install or execute the accepted bytes.

These are controlled scenario results, not a measured real-world attack detection percentage. See [the threat model](docs/THREAT_MODEL.md).

## Verify the implementation

The [benchmark and measured results](docs/MEASUREMENTS.md) cover real v1-to-v2 updates. The [detached approvals guide](docs/APPROVALS.md) shows how maintainers can authorize releases with separate keys.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use real loopback HTTP servers, encrypted keys, downloaded ZIP bundles, actual application self-tests, and separate updater processes. The interruption test kills a subprocess at the activation commit boundary and then verifies recovery in a new process.

Optional report browser checks require Node.js and installed Chrome, but the updater itself does not:

```powershell
node scripts/check-report.mjs .runtime\YOUR-RUN\report.html
```

Set `VU_BROWSER` to another Chromium executable if needed. The checker uses a new profile under `.runtime/` and writes desktop/mobile captures to `.impeccable/review/`.

## Manual publisher and client workflow

Use a new `.runtime/manual` directory. Key operations prompt for the same publisher passphrase, which must contain at least 12 bytes. `VU_KEY_PASSPHRASE` is supported for controlled automation; interactive prompting avoids putting a passphrase in shell history.

```powershell
.\.venv\Scripts\python.exe -m verified_updates publisher init --publisher .runtime/manual/publisher --repository .runtime/manual/repository

.\.venv\Scripts\python.exe -m verified_updates bundle --source demo_app/csv_inspector.py --output .runtime/manual/release-1.zip --app-id csv-inspector --version 1.0.0 --sequence 1

$pendingRelease = .\.venv\Scripts\python.exe -m verified_updates publisher prepare --publisher .runtime/manual/publisher --artifact .runtime/manual/release-1.zip --app-id csv-inspector --version 1.0.0 --sequence 1 | ConvertFrom-Json

.\.venv\Scripts\python.exe -m verified_updates publisher inspect --publisher .runtime/manual/publisher --release $pendingRelease.release_id
.\.venv\Scripts\python.exe -m verified_updates publisher approve --publisher .runtime/manual/publisher --release $pendingRelease.release_id --signer 1
.\.venv\Scripts\python.exe -m verified_updates publisher approve --publisher .runtime/manual/publisher --release $pendingRelease.release_id --signer 2
.\.venv\Scripts\python.exe -m verified_updates publisher publish --publisher .runtime/manual/publisher --release $pendingRelease.release_id
```

`publisher inspect` shows the app, platform, release sequence, artifact size, SHA-256 digest, and verified approval count. Run it before signing and after each approval to show the authorization decision. Each approval checks that the prepared artifact still matches the digest.

In a second terminal, serve only the public repository:

```powershell
.\.venv\Scripts\python.exe -m verified_updates serve --repository .runtime/manual/repository --port 8080
```

In the original terminal, provision the client using the authentic bootstrap root from the publisher, then update:

```powershell
$env:NO_PROXY = "$env:NO_PROXY,127.0.0.1,localhost"
.\.venv\Scripts\python.exe -m verified_updates client init --client .runtime/manual/client --bootstrap .runtime/manual/publisher/bootstrap/root.json --repository-url http://127.0.0.1:8080/ --app-id csv-inspector
.\.venv\Scripts\python.exe -m verified_updates client update --client .runtime/manual/client
.\.venv\Scripts\python.exe -m verified_updates client run --client .runtime/manual/client -- demo_app/sample.csv
```

Client CLI exit codes: `0` updated/current; `3` verification or policy rejection; `4` operational failure; `2` command/configuration error. Structured JSON includes the actual failed stage and underlying error type. `client run` returns the installed application's exit code.

Rotate a targets signing key with `publisher rotate-targets-key --publisher ... --signer 1`. This issues a root update authorized by the existing root quorum and republishes targets with the new authorized key. Rotation of the root-signing keys themselves is not implemented yet.

For a later reference application build, `verified_updates.reference.reference_bundle(directory, sequence, version)` generates a new CSV Inspector bundle. Sequences 2 and later add numeric summaries. The generic `bundle` command packages another single-file Python application supporting `--self-test`.

## Architecture and limitations

Read [architecture](docs/ARCHITECTURE.md), [threat model](docs/THREAT_MODEL.md), and [demo guidance](docs/DEMO.md). Authentic initial provisioning, an uncompromised client, retained client state, and a reasonably trustworthy clock are explicit assumptions. Signing keys are separate from public storage, but the local demo simulates all maintainers on one machine.

The installer supports Python source ZIPs with one entrypoint and retains staged and previous versions. Executable packaging, automatic cleanup, publisher crash recovery and deployment hardening remain open. Detached approvals support a single application and platform per repository. The local key rotation command is for the default demo mode.

## Continue with Claude or another assistant

Start with [CLAUDE.md](CLAUDE.md), [HANDOFF.md](HANDOFF.md), and [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md). The handoff records exact verified results, known gaps, and next steps. It is the source of truth for implementation status.

## Attribution

This project builds on the [official Python TUF implementation](https://github.com/theupdateframework/python-tuf), [TUF specification](https://theupdateframework.github.io/specification/latest/), [securesystemslib](https://github.com/secure-systems-lab/securesystemslib), and [cryptography](https://cryptography.io/). Existing systems such as [tufup](https://github.com/dennisvang/tufup) are relevant prior work. Our contribution is integration, usable release/installation behaviour, and reproducible evaluation.


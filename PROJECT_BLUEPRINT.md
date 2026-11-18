# Secure Software Updates Under Repository Compromise

Status: implementation is underway. Read HANDOFF.md for verified current behaviour and remaining work; this document describes the target scope.

## Decision and purpose

Build a reusable, TUF-based update system for portable Windows applications, a useful reference application that actually updates, and a repeatable adversarial evaluation. The user subsequently authorized deletion of ITC_PROJECT/ and rea/; both were removed. The new implementation lives directly at the workspace root.

The intended user is a developer distributing a small desktop application outside an app store. They need a usable way to publish releases, authorize maintainers, update clients, replace keys, and recover from interrupted installations.

The central security question is: if an attacker controls the update repository, what can they cause an already provisioned, uncompromised client to accept?

The deliverable is a working release and update workflow with measured security behaviour. Its contribution is implementation, integration, and comparative evaluation of an established design. Credit TUF explicitly. Existing tools such as tufup already apply TUF to Python applications; do not claim invention of secure updates or a new cryptographic protocol.

## Security foundation and boundaries

Use the official `python-tuf` metadata APIs and `tuf.ngclient` verification workflow. Use its supported signing backend for Ed25519 and SHA-256 target digests. Pin tested dependency versions during implementation. Do not implement a competing TUF verifier or substitute a custom signed JSON format in the main client.

The client starts with authentic bootstrap root metadata bundled with the trusted initial application distribution. That distribution is an explicit trust assumption. A public key downloaded for the first time from an already compromised update server does not establish publisher identity.

Persist trusted metadata and application release ordering state across updates and restarts. Protect the trusted client installation and its state using the operating system's normal permissions. The local attacker who can rewrite the updater or its trusted state is outside the repository-compromise threat model.

Demonstrate these attacker capabilities:

- Replace or delete repository files and change their unsigned checksums.
- Replay previously captured metadata and releases.
- Mix metadata from different repository publications.
- Withhold current metadata and continue serving stale metadata.
- Possess one release-signing private key when release authorization requires two distinct keys.

Document these limits:

- A repository can deny service. Rejection of an unsafe update preserves the installed application; it cannot force delivery of a new update.
- Expiration limits acceptance of stale metadata and requires an adequately trustworthy client clock. It cannot reveal a withheld update immediately while existing metadata remains valid.
- Rollback checks depend on retained client state. Fresh installations have less history than existing clients.
- A validly authorized harmful release remains authorized. The project does not assess whether application code is safe.
- Compromise of the required signing quorum, the publisher's build environment, or the client host needs a separate analysis.
- Signatures authenticate release artifacts and metadata. They do not encrypt public downloads or independently prove source-code provenance.

## Product scope

### 1. Publisher CLI

Provide commands to initialize a repository, prepare a release, sign metadata, finalize publication, inspect trusted roles, and rotate signing keys.

- Prepare full ZIP release bundles and versioned TUF metadata.
- Bind each release to an application ID, platform, display version, and increasing integer release sequence in signed metadata.
- Use distinct role keys: root, targets, snapshot, and timestamp.
- Configure root and targets roles with two-of-three independent Ed25519 signatures; snapshot and timestamp roles may each use one distinct key.
- Count each authorized signing key once. This is a quorum of ordinary signatures, not a secret-sharing or threshold-signature primitive.
- Support separate signing steps so maintainers can hold separate private keys. A demo with all key files on one machine demonstrates the mechanism, not independent custody.
- Keep private keys outside the repository, its HTTP process, and the presentation console. Store private keys encrypted at rest and accept passphrases through an appropriate interactive mechanism.
- Apply TUF root-rotation requirements, including the required authorization under old and new root policies.
- Prepare publications in a staging area and expose metadata in the appropriate order so clients do not receive partially published state.

### 2. Public update repository

Serve public metadata and artifacts over HTTP in the local lab. Support HTTPS URLs for ordinary deployments; explain why HTTPS and publisher authorization address different trust boundaries.

The repository holds no private signing keys. Keep repository serving separate from publishing and lab orchestration. The lab attack runner can alter a disposable repository copy without obtaining publisher key files.

### 3. Reusable updater library and CLI

Provide an updater that another application can integrate, plus a CLI exercising the same code.

- Initialize with authentic bootstrap root metadata.
- Refresh and verify metadata using `tuf.ngclient`.
- Select the exact intended application and platform, then validate authenticated target length and digest.
- Preserve TUF trusted metadata across process restarts.
- Persist the highest accepted application release sequence. TUF metadata-version rollback protection and application release ordering are separate checks; a semantic-version label alone is not a security policy.
- Perform all authenticity and integrity checks before unpacking or running the downloaded application.
- Bound downloads and unpacking; reject archive paths escaping the staging directory and unsupported links.
- Stage a full release in a separate version directory, perform the approved release's bounded self-test, and activate it through a small atomic state change.
- Retain the previous working installation on rejection or failure. Recover consistently after interruption.
- Keep the launcher/updater and trusted state outside version payload directories. Updating the launcher itself is deferred.
- Return structured outcomes and preserve the underlying verification failure for diagnosis.

First target: a portable Windows application. Linux support, automatic operating-system integration, background services, and patch/delta updates are later extensions.

### 4. Reference application

Build a small local CSV viewer with real utility: open a CSV, search or filter rows, and export the selected data. A later release can add a numeric summary feature.

The launcher should show the installed version and offer an update action. The CSV functionality remains deliberately bounded: it supplies a real application to update and does not become the main engineering effort.

Use a Python desktop implementation and package portable Windows builds. Exercise actual application bundles in the demonstration, including restart into the updated version. Retain user documents and preferences outside version directories.

### 5. Local demonstration and evidence console

Provide a local console showing publication state, signature approvals, installed versions, update outcomes, and adversarial run results. A small Flask application with server-rendered pages and limited JavaScript is sufficient.

The console reads outcomes produced by the actual publisher, updater, and attack runner. It never declares an update verified from an animation, a scenario label, or server-provided claims. Signing occurs through the publisher CLI outside the console process.

The console has no authority to disable verification. Keep deliberately insecure comparison clients in the lab package, outside the main updater's supported configuration.

## Architecture and ownership

```text
Maintainer signing keys
        |
        v
Publisher CLI ---> Public update repository <--- Lab attack runner
                            |
                            v
Authentic bootstrap ---> Updater library/CLI ---> Staged app bundle
root + persistent           |                         |
trusted client state        v                         v
                      Actual run evidence      Atomic activation
                            |                         |
                            v                         v
                      Local console          CSV viewer v1 -> v2
```

Suggested source layout:

```text
verified-updates/
  pyproject.toml
  src/verified_updates/
    publisher/
    client/
    installer/
    contracts/
  demo_app/
  lab/
    attacks/
    baselines/
    console/
  tests/
  docs/
    threat-model.md
    architecture.md
    evaluation.md
    demo-script.md
  scripts/
```

Runtime key material, cached client state, generated releases, repository snapshots, and experiment outputs belong outside source directories and must be excluded appropriately from version control. Check in only clearly identified public fixtures or disposable test keys required by tests.

## Shared component contract

Agree on these interfaces before splitting implementation:

- Signed application identity: app ID, platform, display version, release sequence, and artifact path. The signed target digest and length come from TUF metadata.
- Stable CLI inputs and exit semantics for publication, checking, downloading, installation, and lab runs.
- Client storage locations and ownership, including bootstrap trust, persisted metadata, ordering state, downloads, staged versions, and active-version pointer.
- A versioned JSON result record with run ID, app ID, outcome, reason code, diagnostic detail, and installed release sequence before and after the operation.
- Outcomes distinguish `updated`, `up_to_date`, `rejected`, and operational `failed` cases.
- Reason codes reflect actual first failed checks. Preserve the TUF exception category rather than inventing a verification result to match an expected attack label.
- Scenario setup, run, reset, and evidence-export interfaces. Use disposable run directories and explicit repository/client identities.

The presentation console consumes this contract. Changes require coordination between component owners.

## Demonstration and evaluation

Run independent client processes against a real HTTP repository. Use harmless modified application builds as attack artifacts. Do not use malware or touch unrelated installations.

Required scenarios:

1. Authentic release: publish, verify, install, restart, and show the new CSV feature.
2. Artifact substitution: change a public bundle; reject it and retain the installed version.
3. Artifact plus unsigned-checksum substitution: demonstrate why an unauthenticated checksum is insufficient.
4. Metadata rollback: after the client observes newer state, replay an older signed repository capture; reject it after a client restart too.
5. Stale metadata: serve correctly signed but expired metadata; reject it. Use generated expired fixtures or an isolated test clock rather than changing the user's machine clock.
6. Mixed publication: serve inconsistent versions of timestamp, snapshot, and targets metadata; reject the inconsistency.
7. Insufficient signing quorum: attempt publication with one authorized targets key; show publisher refusal and a forced malformed-publication test exercising client refusal as well. Cryptographically valid surrounding metadata is needed if the experiment claims to reach the targets-threshold check specifically.
8. Authorized key rotation: replace a targets signer under root authorization and accept a newly authorized release. Where key removal is tested, distinguish a client already updated to the new root from a client that has not yet received it.
9. Interrupted download or installation: restart the client and retain or recover a coherent installed version.
10. Wrong application/platform: reject a trusted artifact that is not the one the client requested.

Compare three lab clients using the same benign application releases:

- Unsigned manifest with checksums.
- Signed manifest with no freshness or persistent rollback policy.
- Main TUF-based client with safe installation.

For every scenario capture the actual acceptance decision, verification failure, installed version before/after, and repeatable reproduction command. Measure normal verification time and metadata/download overhead on explicitly recorded hardware and artifact sizes. Do not turn a hand-selected scenario pass count into a general real-world attack detection percentage.

Include a small interoperability check using the official client APIs without the project's UI or installation wrapper to validate publisher output. Explain hashes, signature verification, role authorization, bootstrap trust, expiry, and persistent state in the report and viva.

## Definition of done

- A documented fresh setup can publish and install a genuine release.
- The packaged reference application visibly updates and remains useful afterward.
- All required attack scenarios run against real components and export their results.
- Client state persists across restarts; rejection does not change the active application.
- Key rotation and interrupted-install recovery are demonstrated.
- Another small application can use the updater without importing the demonstration console.
- The threat model, trust assumptions, dependency attribution, measured limitations, and report are complete.
- A single documented lab command prepares the demonstration without hand-editing metadata.

## Build sequence

1. Freeze trust assumptions, package layout, storage model, and component contracts.
2. Build the publisher, HTTP repository, and a verification-only CLI. Prove genuine acceptance and artifact-substitution rejection.
3. Add persisted state, rollback/expiry/quorum scenarios, and authorized rotation.
4. Implement staged installation, recovery, and portable CSV-viewer releases.
5. Add the independent adversarial suite and comparison clients; tests should grow alongside earlier milestones.
6. Build the presentation console from real evidence, then finish measurements, documentation, and demo rehearsal.

Finish the genuine update and artifact-tampering vertical slice before expanding the interface or reference application's features.

## Codex and Claude work split

This is a proposed division for two separately operated assistants. It does not imply that Codex can access or message Claude.

Codex owns the main publisher, updater, trust/state handling, installer, and integration decisions. Claude owns an independently written adversarial suite, the comparison clients, review of security claims, and then the presentation console against agreed contracts.

Both review the threat model and shared contract first. Give components separate file ownership or Git worktrees. Run independent attacks against the real interfaces, and review the other assistant's changes before integration. Avoid simultaneous uncoordinated changes to dependencies, contracts, or the same source files.

Suggested initial Claude prompt:

> Read PROJECT_BLUEPRINT.md. First critique the security claims, trust assumptions, and acceptance criteria. Identify cases where the stated attack would fail to exercise its intended verification check. Then propose the lab scenario interfaces and evidence schema in coordination with the main implementation owner. Your primary ownership is the independent adversarial suite and comparison clients; the local console follows once those interfaces exist. Exercise real client processes and HTTP repository files, preserve actual verification failures, and never fabricate success states. Keep publisher/client core changes separate for review. Credit TUF and distinguish our integration work from its security implementation.

## Primary references

- TUF security model: https://theupdateframework.io/docs/security/
- TUF specification: https://theupdateframework.github.io/specification/latest/
- Official Python implementation: https://github.com/theupdateframework/python-tuf
- Existing related application updater, for comparison and attribution: https://github.com/dennisvang/tufup

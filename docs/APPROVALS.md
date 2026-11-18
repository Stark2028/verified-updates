# Approve a release from two separate machines

The publisher registers three Ed25519 public keys and needs approvals from two of them. Each maintainer generates and keeps an encrypted private key on their own machine. The publisher receives public keys and detached signatures. The default local-demo mode remains available for the one-command lab.

## Set up the publisher

Run the following command on each maintainer's machine. Each maintainer chooses their own passphrase. Transfer only the `.pub.pem` file to the publisher and keep the matching `.pem` private. Exchange the public key files through a channel that lets the publisher confirm whose keys they are.

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python -m verified_updates maintainer keygen --key-dir .runtime/maintainer-keys
```

On the publisher, create a new repository using the three public files. The publisher keeps its own root, snapshot, and timestamp keys. The first public timestamp is available once the first release is approved and published.

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python -m verified_updates publisher init --publisher .runtime/custody/publisher --repository .runtime/custody/repository --maintainer-key .runtime/custody/alice.pub.pem --maintainer-key .runtime/custody/bob.pub.pem --maintainer-key .runtime/custody/carol.pub.pem
& $python -m verified_updates bundle --source demo_app/csv_inspector.py --output .runtime/custody/release.zip --app-id csv-inspector --version 1.0.0 --sequence 1
$pending = & $python -m verified_updates publisher prepare --publisher .runtime/custody/publisher --artifact .runtime/custody/release.zip --app-id csv-inspector --version 1.0.0 --sequence 1 | ConvertFrom-Json
& $python -m verified_updates publisher export-request --publisher .runtime/custody/publisher --release $pending.release_id --output .runtime/custody/request.json
```

Distribute the bootstrap root through an independently trusted channel. For each approval, send `request.json` and `release.zip` to the maintainer. The request is unsigned TUF targets metadata for the single release.

## Review and sign on each maintainer machine

Inspect the request against the trusted root and the actual ZIP. Review the application, version, sequence and artifact digest. Save the `request_sha256` from that inspection. This is the digest of the exact metadata the key will sign. Set `$keyId` to the ID printed when creating this maintainer's key.

```powershell
$review = & $python -m verified_updates maintainer inspect --request request.json --artifact release.zip --root trusted-root.json | ConvertFrom-Json
$review | ConvertTo-Json
# After reviewing the output, use the request digest from that inspection.
& $python -m verified_updates maintainer sign --request request.json --artifact release.zip --root trusted-root.json --key-dir .runtime/maintainer-keys --key-id $keyId --expect-digest $review.request_sha256 --output approval-alice.json
```

Each maintainer returns their approval JSON. Keep the `--expect-digest` value from the reviewed request if preparation and signing take place at different times.

## Collect approvals and demonstrate the decision

```powershell
& $python -m verified_updates publisher import-approval --publisher .runtime/custody/publisher --release $pending.release_id --approval approval-alice.json
& $python -m verified_updates publisher inspect --publisher .runtime/custody/publisher --release $pending.release_id
& $python -m verified_updates publisher publish --publisher .runtime/custody/publisher --release $pending.release_id
# The attempt above fails with one authorized signature. Import the second approval and retry.
& $python -m verified_updates publisher import-approval --publisher .runtime/custody/publisher --release $pending.release_id --approval approval-bob.json
& $python -m verified_updates publisher publish --publisher .runtime/custody/publisher --release $pending.release_id
```

Serve the repository and install it using the client steps in the README, with the custody directory paths. Reimporting the first approval still counts as one signature. An approval for different metadata fails verification. For a classroom rehearsal, separate directories and passphrases show how the files move. Use separate machines to demonstrate separate custody.

The detached workflow supports a single app and platform per repository. The existing local key rotation command serves the default mode. Rotation of externally held targets keys needs its own approval workflow.

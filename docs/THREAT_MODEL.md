# Threat model

## Protected workflow

A client with an authentic initial trust root obtains a release from a repository, verifies its authorization/integrity/freshness under TUF and local application policy, stages it, and activates it after a self-test.

## Attacker and trust assumptions

The repository attacker can replace, delete, replay or mix served public files and manipulate unauthenticated checksums. They do not control the client's executable, bootstrap trust, persistent metadata/order state, or clock. They do not possess the necessary publisher signing quorum. The initial client distribution is obtained through an independently trusted channel.

The demo also isolates the release-quorum check using a one-signature targets fixture with valid snapshot/timestamp support. Constructing that support requires fixture access to those signing keys. This is explicitly broader setup authority than server-only compromise and is not presented as something a server-only attacker can forge.

## What is checked

- TUF root/role signatures and the authorized distinct-key thresholds.
- TUF version, expiry, metadata consistency and artifact length/digest checks.
- An exact application/platform identity in authenticated custom metadata.
- Persisted application sequence and digest policy, distinct from display-version text.
- Safe bounded unpacking and agreement between signed identity and bundle manifest.
- Successful application self-test before committing an active-version change.

## Limits of the current evidence

- A valid signature does not establish that application code is harmless or that a source repository produced a binary.
- A hostile repository can prevent updates. Expiration bounds acceptance of stale metadata; it cannot force delivery of withheld releases.
- The current demo uses one machine and common encrypted-key custody, so it demonstrates signature quorums rather than independent organizational control.
- Correctly signed expired fixtures are created by the test setup. The user's system clock is never modified.
- The process-crash scenario is injected immediately before activation, after the real download, verification, unpacking and self-test. It does not establish power-loss durability or every possible interruption point.
- A self-test runs authorized application code with the user's normal process privileges. It is a health check, not a sandbox.
- Source ZIP installation, no automatic version garbage collection, no root-signer-key rotation CLI, no portable offline approval exchange, and nontransactional publisher state remain known limits.
- The repository HTTP server is a local experiment server, not a hardened public hosting service.
- A failed post-publication self-test can leave the previous application active while security state records the newer accepted sequence. The publisher should issue a still-higher corrective release.
- The HTML/JSON experiment report is local diagnostic evidence, not a signed third-party attestation.

## Validation interpretation

Passing scenarios establish the behaviour recorded for those fixtures. They do not establish universal security, production readiness, or an attack-detection percentage. The underlying TUF protocol and implementation deserve explicit attribution; independently reviewing this integration remains necessary.


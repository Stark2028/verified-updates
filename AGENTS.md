# Project instructions

Read `HANDOFF.md` first, then `PROJECT_BLUEPRINT.md`. `CLAUDE.md` points Claude at the same shared context.

This workspace contains the new Verified Updates project. The user explicitly requested removal of the previous ITC_PROJECT and rea directories; they have been removed. Implement the new project directly in this directory.

Use the official python-tuf verification workflow. Never replace it with a custom verifier or expose an insecure verification bypass in the normal client. Keep private publisher keys outside the served repository and client payload. Validate security decisions against real components and retain actual failure reasons.

Run focused tests for changes and the real HTTP demo when changing publisher/client integration. Distinguish verified behaviour from unimplemented plans. Do not claim production readiness, universal attack prevention, or independent signing custody from a single-machine demonstration.

Update HANDOFF.md before ending each implementation session with completed work, exact commands and results, known limitations, and the next concrete steps. Keep commands compatible with Windows PowerShell. Avoid simultaneous edits by separate assistants to the same files; coordinate interface changes in writing.


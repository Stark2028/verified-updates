# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

The current web surface is a generated offline evidence document. The updater and publisher are Python command-line applications. A Windows desktop reference application and live management console remain planned.

## Stack

Python with official python-tuf verification; self-contained HTML/CSS and small inline JavaScript for the offline report. No frontend package manager or remote assets are required.

## Users

Developers distributing small applications, and students/evaluators inspecting a BTech cryptography project. The user explicitly values meaningful behaviour, demonstrability, and implementation quality over a deadline.

## Product Purpose

Publish authorized releases, verify them under repository-compromise scenarios, install safely, and preserve reproducible evidence. An evaluator should be able to inspect the actual acceptance/rejection reasons and distinguish the implemented guarantees from their assumptions.

## Operating Context

Local Windows development, real loopback HTTP repository, separate client processes, encrypted disposable publisher keys, generated JSON evidence, and an offline HTML report.

## Capabilities and Constraints

The implemented application format is a Python source ZIP with a declared self-test and entrypoint. Keys remain outside the served repository. Signing identities are simulated on one machine. Verification decisions come from actual client execution; report content must never fabricate successful checks.

## Evidence on Hand

Integration tests under tests/, real demo runs under .runtime/, and report generation in verified_updates/report.py. HANDOFF.md records the current commands and verified results.

## Product Principles

- Preserve actual failures and their causes.
- Make trust assumptions inspectable.
- Keep verification reusable independently of the presentation surface.
- Provide reproducible commands and durable continuation context.


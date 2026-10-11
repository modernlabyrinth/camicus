# Contributing

This is an unreleased local alpha candidate. A public repository, maintainer and
contribution intake have not been established. This file describes the intended
contribution process once those routes exist.

Start with a reproducible fictional failing example and the expected bounded
behavior. Keep a change focused on the declared weekly-brief contract. Add a test
that fails before the fix, run `python3 -I -S tests/run.py`, and disclose the actual
Python/macOS/filesystem tested. Never commit credentials, private receipts,
client exports, machine inventories or raw agent transcripts.

Input constraints, privacy-safe diagnostics, no-clobber publication, exact source
bindings and truthful unknown/failure states are part of the interface. Changes
to them need explicit contract review. Live connectors, automatic repair, network
calls, background services and global agent settings need a separate design.

For a release, review the exact commit and archive digest, run the supported
interpreter matrix, and repeat both native-harness demonstrations when packaged
bytes change. Version `0.1.0` is unreleased; it is not a promise of stable APIs.
Result tool-version matching is exact. Future releases must document changes and
compatibility; never silently rewrite old receipts or replace a tagged artifact.

The code and documentation were developed with AI assistance for Modern Labyrinth.
Runtime and tests have no third-party package dependencies. The archive bundles
only this project's explicit runtime allowlist and MIT license. Python itself is
supplied separately by the user. No upstream application code was incorporated.
The license text follows the [OSI MIT license](https://opensource.org/license/mit).
Contributors must identify copied material, preserve required notices and have
the right to submit it under this project's MIT license. Do not claim a full
legal title search or an infringement guarantee from this provenance statement.

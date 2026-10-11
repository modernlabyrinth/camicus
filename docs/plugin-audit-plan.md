# Private plugin and Mac audit milestone

Approved direction: make the existing local checker usable through Codex and
Claude Code plugins, then add a first read-only Mac audit. The approved product and plugin name is Camicus. Existing Python package and
version-1 schema identifiers retain `minoetic` for compatibility. This work does not publish a public release.

## Design

One Python standard-library engine, two assistant manifests, shared skills.
Keep the weekly-brief contract unchanged. Add `audit-mac --workspace ABSOLUTE_PATH
--output NEW_NAME.json`, using the existing descriptor-relative, exclusive,
private result writer. Mac results have their own schema and are not accepted by
weekly-brief `verify`; rerun the audit into a new file to observe current state.

The initial Mac scope is FileVault, System Integrity Protection, Gatekeeper,
the application firewall, stealth mode, and TCP listeners visible to the current
user. Use fixed absolute system commands, no shell, no sudo, bounded time and
output, and no environment/credential discovery. Missing tools, unexpected output,
permission failures and truncation are unobserved, never a passing check. Network
listeners are observations requiring interpretation, not vulnerabilities. Do not
claim whole-device security, internet reachability, malware absence or complete
process coverage. Little Snitch rules and executable provenance are explicitly
outside this first contract. No network requests, setting changes or repairs.

Package from an explicit allowlist, with the executable archive and its SHA-256,
two shared workflow skills, manifests, license and installation guide. Skill paths
resolve from their own package location; installation never depends on a source
checkout. Native tool permissions stay in force. No background hooks or MCP server
are needed for these command-based workflows. Outputs remain private and are not
included in distributable packages.

## Implementation and acceptance

1. Add audit collectors/parsers and fixture-based failure tests; integrate CLI and
   archive allowlist. Prove denied/unknown/truncated observations remain explicit,
   output conflict prevents collection, and publication uses existing protections.
2. Add portable/Codex/Claude manifests and deterministic plugin builder with shared
   skills. Test allowlist, embedded executable hash, relocation, no-overwrite and
   unchanged weekly-brief behavior. Validate with native plugin tooling.
3. Run the complete suite and a live read-only Mac audit into private storage.
   Check the actual saved result; do not expose detailed machine evidence in Git.
   Exercise native discovery/install in task-scoped configuration where supported.
4. Independently review exact changed files and package, fix material findings,
   record actual verification and integration limitations, and deliver a private
   installable candidate plus researched naming recommendations.

Semantic-review disposition: exact command outcomes, schemas, hashes and native
plugin loading use code/source verification. Naming preferences are editorial;
web overlap research is not trademark clearance.

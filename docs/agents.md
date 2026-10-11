# Codex and Claude adapter

The packaged Camicus plugin is the recommended setup for new private testing.
See [plugin installation](plugins.md) for both native hosts and the two included
skills. The path-based adapter below remains available for existing weekly-brief
workflows. The Python package and old result schema identifiers remain `minoetic`
for compatibility; new plugin and executable names are `camicus`.

Both harnesses use [one shared skill](../skills/minoetic/SKILL.md). The checker is
a reviewed executable archive, not an MCP server or background agent. It requires
authorized local command/file access. A successful read does not authorize a
write, upload, live-connector operation or source repair.

## Codex

For this local alpha, ask Codex to read the shared skill by its exact path, then
provide the reviewed archive path, its expected SHA-256 and the explicit workspace.
Codex can invoke the archive with its native command tool. This does not require
global skill installation. A future installation may copy this same skill into
the user's configured skill-discovery directory after explicit selection; do not
assume another user's directory or rewrite their configuration.

## Claude

Provide the same skill path/content, reviewed archive and explicit workspace to
the native Claude session. Its Bash/file tools must be authorized for those paths.
Keep the selected login and normal permission controls. Do not switch accounts,
use API billing, or bypass a denied tool call to manufacture a passing demo.
Manual skill reading works without modifying global Claude settings; any later
discovery installation should point to this same maintained source.

## Evidence and limits

For a native demonstration, preserve actual tool invocation events and exit codes,
archive digest, fresh result run ID and SHA-256. For a weekly brief, then perform
read-only `verify`. For a Mac audit, rerun into a fresh filename when a new
observation is needed; weekly `verify` does not accept the Mac schema.
Record the actual returned model identity if exposed; a caller label is not model
evidence. A shell command outside the native harness does not prove that adapter.
Use fictional inputs for demonstrations. Keep raw events private and never copy
private source material into the repository. Rebuilds that change the archive
digest invalidate old demonstration bindings until repeated.

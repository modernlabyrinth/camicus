# Local weekly-brief contract

Version 1 reads only `project.json` and `tasks.json` in an explicitly selected workspace.
Both contain `schema_version: "minoetic.weekly-input/1"`, matching `project_id`, and
an `as_of` timestamp formatted as UTC `YYYY-MM-DDTHH:MM:SSZ`.
Project adds `summary`; tasks adds `tasks`, an array of `{id, title, state}`.
States are `todo`, `doing`, `done`, `blocked`. Extra fields are rejected.

Inputs are limited to 1 MiB each, eight container levels and 1,000 tasks.
Identifiers match `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`. Summary is 1–2,000 code points;
titles 1–240. Blank text, C0/C1 controls, unpaired surrogates, duplicate keys/IDs,
nonfinite numbers and invalid UTF-8 are rejected. Freshness permits declarations
up to seven days old or five minutes future, inclusive. A declaration is not
proof of business truth; filesystem mtime does not replace it.

The brief copies project context and both timestamps, counts all selected tasks
by state, and lists every blocker in ID order. Independent invariants check it.
Results use `minoetic.weekly-result/1`, contract `weekly-brief/1`, tool version
`0.1.0`, and scope `local-weekly-brief`. The maximum result is 2 MiB of compact
UTF-8 JSON. Tool-version compatibility is exact. Results are unsigned and private;
they contain source context, blocker IDs/titles and input hashes.

`check` returns 0 for a passed observation saved successfully, 1 for an observed
failure, 2 for checks that could not be completed, and 3 for invocation, internal,
or publication errors. A failure outranks an unavailable observation. Unsafe or
uninspectable workspaces receive no writes. For accepted workspaces, destination
preflight precedes input reads; an existing destination is never overwritten.
Case-folded equivalents of both source basenames are reserved even when those
sources are absent, covering case-insensitive filesystems. Workspaces with extended
macOS ACLs are rejected conservatively. Native descriptor ACL inspection must be
available; the newly created temporary descriptor is also checked before private
bytes are written. The checker never removes an existing folder's ACL to proceed.
Every saved result has the ordered ten required checks, source evidence or null,
and a brief only when all required checks pass. Late source changes or denied
observations invalidate the candidate. Publication success follows file fsync,
exclusive hard linking, temporary-link cleanup and directory fsync. A later
error can leave a complete final file without a successful exit. Preserve it;
use a new filename for a new run. No power-loss guarantee is asserted.

`verify` writes nothing. It validates the recorded schema and historical outcome,
checks current freshness, exact source-byte bindings and brief invariants, then
re-observes both sources and the receipt. It adds `result_read`, `result_schema`,
`recorded_outcome`, `source_binding` and `result_stability` assessments. Failed or
unknown historical runs cannot become passed. Missing historical evidence is
explicitly unknown; repaired inputs require a new `check`. Anyone who can edit
these unsigned files can fabricate a consistent history. Verification does not
authenticate past execution or prove source claims true.

CLI diagnostics contain only bounded check IDs, states, reason codes, source
aliases and structural field references. They contain no source prose, task IDs,
hashes, raw exception messages or workspace paths. See troubleshooting for fixed
repair guidance. The weekly-brief workflow performs no network or subprocess operations; it
does not sandbox the calling assistant or prevent folder synchronization.

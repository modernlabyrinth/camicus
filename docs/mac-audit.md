# Read-only Mac audit contract

`audit-mac --workspace ABSOLUTE_PATH --output NEW_NAME.json` observes fixed local
macOS controls. Use macOS 14 or newer and Python 3.11–3.14. The explicit workspace
must satisfy the existing ownership, permissions, symlink and ACL protections.
Output preflight runs before every probe; an existing output prevents collection.
Publication is exclusive and uses mode 0600. No weekly input files are required.

The engine exports `minoetic.mac_audit.run_audit(path, filename, now)` and returns
the existing `workflow.Outcome`. Its checks test FileVault, SIP, Gatekeeper and
application firewall enabled status. Disabled controls fail the stated policy.
Stealth mode is informational: either recognized setting is an observed check.
TCP listener success means only that a nonempty, recognized snapshot was collected.
It does not mean that a listener or device is safe. The overall result summarizes
these limited checks, not a whole-device security assessment.

Collectors use only these fixed absolute argv, without a shell:

- `/usr/bin/fdesetup status`
- `/usr/bin/csrutil status`
- `/usr/sbin/spctl --status`
- `/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate` and `--getstealthmode`
- `/usr/sbin/lsof -nP -iTCP -sTCP:LISTEN -Fpcn`

Each command has a five-second runtime budget and a combined stdout/stderr cap of
128 KiB. Both pipes are drained incrementally; overflow or timeout kills and reaps
the child. stdin is closed, inherited descriptors are closed, and the environment
contains only `LC_ALL=C` and a system-only PATH. No sudo, network requests,
credential discovery, setting changes, repairs or executable provenance checks
occur. Listeners reflect current-user visibility and may omit other processes.

Results use the distinct `minoetic.mac-audit/1` schema. Each command's captured
stdout and stderr bytes are embedded as base64, with separate SHA-256 hashes,
byte counts, fixed argv, observation time, return code and collection reason.
Normalized findings are booleans for recognized controls or a list of observed
PID, command, file descriptor and endpoint records for listeners. Command names come from lsof's
command field; process command-line arguments and arbitrary environment variables
are not collected. The raw evidence is private and may include local process and
endpoint details. Do not include audit results in packages or tracked fixtures.

Missing commands, denied execution, nonzero exits, unexpected stderr, unknown
formats, empty lsof output and truncated observations are `not_checked`, never
passing. A partial capture remains evidence of failure, not a complete snapshot.
A recognized disabled policy check is `failed`. Exit codes follow the existing
Outcome convention: 0 passed, 1 failed, 2 not checked, 3 checker error. Publication
failure returns checker error without claiming a saved result. Diagnostics are
fixed reason codes and never reproduce command output.

These are unsigned local records. The weekly `verify` workflow intentionally does
not accept this schema. Rerun into a new filename to observe current state. Tests
use fictional fixtures and synthetic bounded subprocesses; they do not audit the
machine running the suite.

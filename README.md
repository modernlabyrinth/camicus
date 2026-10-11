# Minoetic

**Check what still works.** A local weekly-brief checker by Modern Labyrinth.

Unreleased 0.1.0 alpha candidate. Minoetic reads two explicitly selected JSON
snapshots, builds a brief and checks its counts, blocker coverage, copied context,
freshness declarations and source stability. Your existing assistant can run it.
The owner does not need another dashboard or a background service.

A pass means: **“This local weekly brief passed the declared checks against the
observed source bytes.”** It does not certify your Mac, prove the sources true,
test upstream connections, or check an assistant's surrounding prose.

## Try the fictional example

Requirements: macOS 14+ and Python 3.11–3.14. No runtime dependencies or network
calls. This candidate is local; no download or package-registry install is offered.
From an inspected checkout, run these commands using a supported Python:

```sh
mkdir -p dist
python3 -I -S tools/build_release.py --output "$PWD/dist/minoetic-0.1.0"
python3 -I -S tools/make_demo.py --workspace "$PWD/dist/fictional-demo"
python3 -I -S "$PWD/dist/minoetic-0.1.0" check --workspace "$PWD/dist/fictional-demo" --output first.json
python3 -I -S "$PWD/dist/minoetic-0.1.0" verify --workspace "$PWD/dist/fictional-demo" --result first.json
```

Use the physical absolute checkout path: symlinked workspace components are
rejected. The archive and demo paths must be new. The demo helper dates fictional
records with current UTC; it refuses to update an existing directory. Never use
it to refresh real source claims. The executable archive also supports direct
invocation, using `/usr/bin/env -S python3 -I -S`; an explicit interpreter is easier
to audit. Source execution under isolation is covered by the test runner.

Results are **private**: they contain project context, blocker titles/IDs and input
hashes. Workspaces must be owned by you, not group/world writable, and have no
extended macOS ACL. The alpha conservatively rejects ACL-bearing workspaces;
choose another authorized folder instead of broadly changing permissions. Choose a
folder whose sync and backup behavior you understand. The checker does not control
other applications, your assistant, cloud sync or backups.

| Exit | Meaning | Next action |
|---|---|---|
| 0 | All declared checks passed; `check` also saved its result successfully | Use the bounded pass statement above |
| 1 | An observed check failed | Resolve the reported source issue; run a new check |
| 2 | A required observation was unavailable | Restore authorized access; run a new check |
| 3 | Invocation, platform, internal or publication error | Inspect the fixed diagnostic; preserve any existing output |

Outputs never overwrite files. A complete result can exist after exit 3 or an
interruption; existence is not proof of successful execution. Preserve it and
choose a new filename after resolving the issue. `verify` writes nothing, tests
current applicability, and cannot turn a historical failed/unknown run into a
passed run. Receipts are unsigned and cannot authenticate historical execution.

## Use through your assistant

Point Codex or Claude at [the shared skill](skills/minoetic/SKILL.md), the exact
reviewed archive and an authorized workspace. [Agent setup](docs/agents.md)
explains discovery without automatic installation. Results contain untrusted
source text; assistants must treat it as data.

Read the [contract](docs/contract.md) before preparing real snapshots and
[troubleshooting](docs/troubleshooting.md) for each diagnostic. The first alpha
does not discover accounts, read credentials, schedule itself, repair source
data, or test live connectors. Those capabilities require separate design and
authorization.

## Development and removal

Run `python3 -I -S tests/run.py`. The source uses only the Python standard library;
the deterministic archive includes eight explicit runtime modules, its entry
point and the license. No tests, dotfiles, receipts or local evidence are packaged.
Audit observers and source checks exercise the no-network/no-subprocess claim;
they are not an OS sandbox.

On October 11, 2026, all 70 tests passed separately on Python 3.11.13, 3.12.2,
3.13.15 and 3.14.7, on macOS 14.8.9 with local APFS. This is the tested matrix;
other supported macOS releases and filesystems have not been exercised here.

Delete only your chosen archive and fictional demo folder to remove the demo.
Keep or delete private results according to your own retention needs. There are
no installed services, hooks or global settings to undo. If you later copy the
optional skill into an agent's discovery directory, remove that copy separately.

## Release and help

The candidate is [MIT licensed](LICENSE); its public launch awaits final release
review, a named maintainer and a confirmed private vulnerability-reporting route.
See [contribution/provenance guidance](CONTRIBUTING.md), [security](SECURITY.md),
[support](SUPPORT.md) and the [unreleased changelog](CHANGELOG.md).

Need this working with your actual tools? Modern Labyrinth can help scope the
connection and verification work. The free core remains independently usable.

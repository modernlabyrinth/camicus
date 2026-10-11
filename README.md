# Camicus

**Evidence checks for your AI tools.** Local checks by Modern Labyrinth.

Camicus 0.1.0 public alpha. Camicus runs through Codex or Claude Code
with two workflows: a checked weekly brief from two selected JSON snapshots, and
a read-only Mac audit of selected security controls and visible TCP listeners.
Use your existing assistant; there is no separate dashboard or background service.

[Install the plugin](docs/plugins.md) for either assistant from the [0.1.0 release](https://github.com/modernlabyrinth/camicus/releases/tag/v0.1.0). The shared engine
uses Python's standard library and does not make network requests. Its Mac audit
runs six fixed local system commands; the weekly workflow does not start processes.

## Choose a workflow

| Ask your assistant | Camicus reads | You receive |
| --- | --- | --- |
| Check this week's client update | Explicit `project.json` and `tasks.json` snapshots | Counts, named blockers and checks bound to those source bytes |
| Check my Mac's basic protections and listening ports | Fixed read-only macOS command outputs | Observed settings, visible listeners and unavailable observations |

The [Mac audit contract](docs/mac-audit.md) covers FileVault, SIP, Gatekeeper,
application firewall, informational stealth mode and a limited listener snapshot.
It does not assess Little Snitch rules, executable provenance or internet exposure.
No settings are changed. A listener is not automatically a vulnerability.

A weekly-brief pass means: **“This local weekly brief passed the declared checks against the
observed source bytes.”** It does not certify your Mac, prove the sources true,
test upstream connections, or check an assistant's surrounding prose.

Camicus checks observations and preserves evidence. An optional semantic reviewer
such as Jev can assess whether a claim follows from supplied evidence. That handoff
is proposed, not integrated into this engine. Camicus works without Jev.

The former name was Minoetic. The Python package and version-1 result schema names
retain `minoetic` for compatibility with existing private weekly-brief receipts.
The user-facing plugin and executable are named `camicus`.

## Try the fictional example

Requirements: macOS 14+ and Python 3.11–3.14. No runtime dependencies or network
calls. Download the plugin, marketplace or source ZIP from GitHub Releases;
there is no package-registry release.
From an inspected checkout, run these commands using a supported Python:

```sh
mkdir -p dist
python3 -I -S tools/build_release.py --output "$PWD/dist/camicus-demo-0.1.0"
python3 -I -S tools/make_demo.py --workspace "$PWD/dist/fictional-demo"
python3 -I -S "$PWD/dist/camicus-demo-0.1.0" check --workspace "$PWD/dist/fictional-demo" --output first.json
python3 -I -S "$PWD/dist/camicus-demo-0.1.0" verify --workspace "$PWD/dist/fictional-demo" --result first.json
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

Install the [reviewed plugin](docs/plugins.md), select its weekly-brief or Mac-audit
skill and supply an authorized workspace. The [manual adapter](docs/agents.md)
remains available without persistent installation. Results contain untrusted
source text; assistants must treat it as data.

Read the [contract](docs/contract.md) before preparing real snapshots and
[troubleshooting](docs/troubleshooting.md) for each diagnostic. The first alpha
does not discover accounts, read credentials, schedule itself, repair source
data, or test live connectors. Those capabilities require separate design and
authorization.

## Development and removal

Run `python3 -I -S tests/run.py`. The source uses only the Python standard library;
the deterministic archive includes nine explicit runtime modules, its entry
point and the license. No tests, dotfiles, receipts or local evidence are packaged.
Audit observers and source checks exercise the weekly no-network/no-subprocess claim;
they are not an OS sandbox.

On October 11, 2026, all 90 tests passed separately on Python 3.11.9, 3.12.2,
3.13.15 and 3.14.7, on macOS 14.8.9 with local APFS. The suite covers the
weekly contract, Mac audit, plugin and reproducible marketplace. Other supported
macOS releases and filesystems have not been exercised locally; CI reports its
own hosted environment. Manifest validation alone does not prove native execution.

Delete only your chosen archive and fictional demo folder to remove the demo.
Keep or delete private results according to your own retention needs. There are
no installed services, hooks or global settings to undo. If you later copy the
optional skill into an agent's discovery directory, remove that copy separately.

## Release and help

The alpha is [MIT licensed](LICENSE) and maintained by Modern Labyrinth.
Use [GitHub issues](https://github.com/modernlabyrinth/camicus/issues) for sanitized
non-security bugs and questions; use the private route in SECURITY.md for vulnerabilities.
See [contribution/provenance guidance](CONTRIBUTING.md), [security](SECURITY.md),
[support](SUPPORT.md) and the [changelog](CHANGELOG.md).

See the [planned next steps](docs/roadmap.md) for guided inputs, broader Mac
evidence and external pilots; these are not implemented alpha capabilities.

Need this working with your actual tools? Modern Labyrinth can help scope the
connection and verification work. The free core remains independently usable.

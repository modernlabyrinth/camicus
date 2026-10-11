# Private local plugin

Build from the reviewed source checkout:

```sh
python3 -I -S tools/build_plugin.py --output /absolute/path/to/new-camicus-plugin
```

The output must be a new absolute directory with existing, symlink-free parent
components; on macOS resolve `/tmp` or `/var` aliases to their `/private` paths. The builder stages privately and
publishes atomically without overwriting. Its explicit allowlist includes three
manifests, two workflow skills, the standard-library executable, its SHA-256,
license and this guide. It excludes project data, saved results, credentials,
tests and repository metadata. The private plugin identifier is `camicus`. The folder can move without rebuilding.

Use Python 3.11–3.14 on macOS. Each skill resolves the executable relative to its
own location and requires the embedded digest before native execution. A digest
checks integrity against the reviewed package; it does not establish who authored
it. Review the package before loading it. The plugin has no MCP server, hooks,
network integration or background process. Native permissions govern every run.

## Claude Code session

Validate the built folder, then load it for one explicitly selected session:

```sh
claude plugin validate /absolute/path/to/new-camicus-plugin --strict
claude --plugin-dir /absolute/path/to/new-camicus-plugin
```

Use `/camicus:weekly-brief` or `/camicus:mac-audit` with an explicitly authorized
workspace. `--plugin-dir` avoids persistent installation. The manifest uses
`.claude-plugin/plugin.json`, with shared skills under `skills/`. This package
includes `bin/`; it targets local Claude Code, not claude.ai/Cowork installation.
See [Claude plugin reference](https://code.claude.com/docs/en/plugins-reference)
and [session loading](https://code.claude.com/docs/en/plugins).

## Codex local marketplace

Codex uses root `plugin.json`; `.codex-plugin/plugin.json` is a compatibility
fallback. For a task-owned marketplace folder, copy this package to
`plugins/camicus`, and create `.agents/plugins/marketplace.json` at its root:

```json
{
  "name": "camicus-private",
  "plugins": [{
    "name": "camicus",
    "source": {"source": "local", "path": "./plugins/camicus"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity"
  }]
}
```

Relative paths resolve from the marketplace root. For supported repo discovery,
open that trusted project and select the local plugin; enable it with the
project's `.codex/config.toml` only after explicit selection:

```toml
[plugins."camicus@camicus-private"]
enabled = true
```

The installed CLI exposes `codex plugin marketplace add /absolute/marketplace`
and `codex plugin add camicus@camicus-private`. These commands persist
marketplace/plugin configuration, so use them only in explicitly selected
configuration, never as an automatic connectivity test. The builder does not
install anything or alter user configuration. See the current
[OpenAI package and local marketplace specification](https://developers.openai.com/plugins/build/plugins).

## Workflow boundary

Weekly brief: `check --workspace ABSOLUTE --output NEW.json`, followed by
`verify --workspace ABSOLUTE --result NEW.json`. Mac audit:
`audit-mac --workspace ABSOLUTE --output NEW.json`. Outputs are new basenames
inside the selected workspace. Mac results are not weekly-brief verify inputs.
Keep results private and report only bounded observations. Native loading and
actual execution need their own evidence; manifest validation alone proves neither.

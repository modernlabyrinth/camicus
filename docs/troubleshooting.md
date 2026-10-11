# Diagnostic guide

Use the fixed reason and source alias printed by the checker. Do not paste private
results or raw input into public issues. Preserve existing outputs; a new run uses
a new basename. Never change a real source's `as_of` just to make it pass.

| Reason | Action |
|---|---|
| `ok` | No repair for this check |
| `dependency_unavailable` | Resolve the earlier failed or unavailable prerequisite |
| `missing_file` | Supply the authorized selected file from its real source |
| `read_denied` | Restore authorized read access without broadening unrelated permissions |
| `unsafe_path` | Select an absolute workspace without symlinks/traversal and a plain result basename |
| `unsafe_workspace` | Choose a user-owned workspace with no extended ACL and no group/world write access |
| `not_regular` | Supply a regular JSON file, not a directory or special file |
| `multiple_links` | Use an independent regular copy of the authorized input/result |
| `too_large` | Reduce the selected snapshot within the published byte limit |
| `invalid_utf8` | Export the authorized source as UTF-8 |
| `invalid_json` | Correct JSON syntax in the source export |
| `duplicate_key` | Remove ambiguous duplicate object keys in the export |
| `nonfinite_number` | Remove nonfinite numeric values from the export |
| `excessive_depth` | Use the documented shallow input schema |
| `schema_mismatch` | Match the exact supported schema, fields, types and timestamp format |
| `invalid_text` | Correct blank, overlong or control-bearing text in the source export |
| `invalid_id` | Use a bounded identifier allowed by the contract |
| `duplicate_task_id` | Resolve repeated task IDs in the source system/export |
| `project_mismatch` | Select exports belonging to the same intended project |
| `stale_as_of` | Obtain a genuinely current authorized snapshot |
| `future_as_of` | Confirm the local clock and source's real UTC observation time |
| `brief_mismatch` | Preserve evidence and run a new check from the intended unchanged sources |
| `source_changed` | Finish source edits and start a new observation with a new output name |
| `source_unobserved` | Restore authorized observation access and start a new check |
| `invalid_result` | Preserve the invalid receipt and create a new check; do not edit it into a pass |
| `unsupported_result_version` | Use the receipt's exact supported tool version or create a new check |
| `source_binding_mismatch` | Select the intended source snapshots or create a new check for current data |
| `historical_evidence_missing` | Create a new check after resolving the missing historical input |
| `historical_failed` | Keep the old failure; run a new check after resolving its cause |
| `historical_not_checked` | Keep the old unknown result; run a new check after restoring observation |
| `invalid_invocation` | Follow `--help`, using single relative `.json` result names and all required flags |
| `unsupported_platform` | Use macOS 14+ with Python 3.11–3.14 and required descriptor/ACL inspection APIs |
| `output_conflict` | Preserve the existing entry and choose a new output basename |
| `publication_failed` | Preserve any complete final file; check authorized folder/filesystem access before a new run |
| `internal_error` | Preserve local evidence; use the support policy before retrying |

Observed failures return 1; unavailable observations return 2 unless another check
failed. Invocation/publication/internal errors return 3. A saved complete file
after a nonzero process result does not establish success. An OS signal can end
the process outside these handled exits; do not infer success from missing output.

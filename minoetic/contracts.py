"""Closed, bounded JSON contracts and stable diagnostics."""
from datetime import datetime, timedelta, timezone
import json
import math
import re
from uuid import UUID
from .models import Check, JsonObject, Problem, Project, Task, Tasks, stamp

SOURCE_LIMIT = 1_048_576
RESULT_LIMIT = 2_097_152
INPUT_VERSION = "minoetic.weekly-input/1"
RESULT_VERSION = "minoetic.weekly-result/1"
CONTRACT_VERSION = "weekly-brief/1"
SCOPE = "local-weekly-brief"
STATES = ("todo", "doing", "done", "blocked")
CHECK_IDS = ("workspace_boundary", "project_read", "project_schema", "project_freshness",
             "tasks_read", "tasks_schema", "tasks_freshness", "project_identity",
             "brief_invariants", "source_stability")
LIMITATIONS = ("Source claims are not verified as true.",
              "Upstream connections and agent prose are not checked.",
              "Checks apply only at observed checkpoints.",
              "This is unsigned local evidence, not a security assessment.")
REASONS = frozenset("""ok dependency_unavailable missing_file read_denied unsafe_path
unsafe_workspace not_regular multiple_links too_large invalid_utf8 invalid_json
duplicate_key nonfinite_number excessive_depth schema_mismatch invalid_text invalid_id
duplicate_task_id project_mismatch stale_as_of future_as_of brief_mismatch source_changed
source_unobserved invalid_result unsupported_result_version source_binding_mismatch
historical_evidence_missing historical_failed historical_not_checked invalid_invocation
unsupported_platform output_conflict publication_failed internal_error""".split())
UNKNOWN_REASONS = frozenset(("dependency_unavailable", "read_denied", "source_unobserved",
                             "historical_evidence_missing", "historical_not_checked"))
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
FIELD = re.compile(r"/(?:schema_version|project_id|summary|as_of|tasks(?:/[0-9]{1,4}(?:/(?:id|title|state))?)?)\Z")


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Problem("duplicate_key")
        value[key] = item
    return value


def _number(value):
    result = float(value)
    if not math.isfinite(result):
        raise Problem("nonfinite_number")
    return result


def _constant(_value):
    raise Problem("nonfinite_number")


def _decode(data: bytes, limit: int):
    if len(data) > limit:
        raise Problem("too_large")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Problem("invalid_utf8") from None
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 8:
                raise Problem("excessive_depth")
        elif char in "]}":
            depth -= 1
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=_constant, parse_float=_number)
    except (ValueError, RecursionError):
        raise Problem("invalid_json") from None


def _object(value, fields):
    if type(value) is not dict or value.keys() != set(fields):
        raise Problem("schema_mismatch")


def _id(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise Problem("invalid_id")
    return value


def _text(value, maximum):
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum or not value.strip()
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise Problem("invalid_text")
    return value


def parse_time(value) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise Problem("schema_mismatch")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise Problem("schema_mismatch") from None


def _input(data, extra):
    value = _decode(data, SOURCE_LIMIT)
    _object(value, ("schema_version", "project_id", "as_of", extra))
    if value["schema_version"] != INPUT_VERSION:
        raise Problem("schema_mismatch")
    return value, _id(value["project_id"]), parse_time(value["as_of"])


def parse_project(data: bytes) -> Project:
    value, project_id, as_of = _input(data, "summary")
    return Project(project_id, as_of, _text(value["summary"], 2000))


def parse_tasks(data: bytes) -> Tasks:
    value, project_id, as_of = _input(data, "tasks")
    rows = value["tasks"]
    if type(rows) is not list or len(rows) > 1000:
        raise Problem("schema_mismatch")
    tasks, seen = [], set()
    for row in rows:
        _object(row, ("id", "title", "state"))
        ident, title = _id(row["id"]), _text(row["title"], 240)
        if row["state"] not in STATES:
            raise Problem("schema_mismatch")
        if ident in seen:
            raise Problem("duplicate_task_id")
        seen.add(ident)
        tasks.append(Task(ident, title, row["state"]))
    return Tasks(project_id, as_of, tuple(tasks))


def freshness(as_of: datetime, now: datetime, source: str) -> Check:
    reason = ("stale_as_of" if as_of < now - timedelta(days=7)
              else "future_as_of" if as_of > now + timedelta(minutes=5) else "ok")
    return Check(source + "_freshness", "passed" if reason == "ok" else "failed", reason, source)


def aggregate(checks: tuple[Check, ...]) -> str:
    if any(c.state == "failed" for c in checks):
        return "failed"
    return "passed" if checks and all(c.state == "passed" for c in checks) else "not_checked"


def encode_result(result: JsonObject) -> bytes:
    data = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(data) > RESULT_LIMIT:
        raise Problem("too_large")
    return data


def validate_brief_shape(value):
    _object(value, ("project_id", "project_summary", "source_as_of", "task_counts", "blocked_tasks"))
    _id(value["project_id"]); _text(value["project_summary"], 2000)
    _object(value["source_as_of"], ("project", "tasks"))
    for time in value["source_as_of"].values():
        parse_time(time)
    counts = value["task_counts"]
    _object(counts, ("total", *STATES))
    if any(type(n) is not int or not 0 <= n <= 1000 for n in counts.values()):
        raise Problem("invalid_result")
    if counts["total"] != sum(counts[s] for s in STATES):
        raise Problem("invalid_result")
    rows = value["blocked_tasks"]
    if type(rows) is not list or len(rows) != counts["blocked"]:
        raise Problem("invalid_result")
    identifiers = []
    for row in rows:
        _object(row, ("id", "title"))
        identifiers.append(_id(row["id"])); _text(row["title"], 240)
    if identifiers != sorted(set(identifiers)):
        raise Problem("invalid_result")


def _validate_result(value, tool_version):
    _object(value, ("schema_version", "tool_version", "contract_version", "run_id", "started_at",
                    "finished_at", "scope", "sources", "checks", "overall", "brief", "limitations"))
    if (value["schema_version"] != RESULT_VERSION or value["tool_version"] != tool_version
            or value["contract_version"] != CONTRACT_VERSION):
        raise Problem("unsupported_result_version")
    if value["scope"] != SCOPE or value["limitations"] != list(LIMITATIONS):
        raise Problem("invalid_result")
    ident = UUID(value["run_id"])
    if ident.version != 4 or str(ident) != value["run_id"]:
        raise Problem("invalid_result")
    start, end = parse_time(value["started_at"]), parse_time(value["finished_at"])
    if end < start:
        raise Problem("invalid_result")
    _object(value["sources"], ("project", "tasks"))
    for evidence in value["sources"].values():
        if evidence is None:
            continue
        _object(evidence, ("sha256", "byte_length", "as_of", "read_at"))
        if (not isinstance(evidence["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", evidence["sha256"])
                or type(evidence["byte_length"]) is not int or not 0 <= evidence["byte_length"] <= SOURCE_LIMIT
                or not start <= parse_time(evidence["read_at"]) <= end):
            raise Problem("invalid_result")
        if evidence["as_of"] is not None:
            parse_time(evidence["as_of"])
    rows = value["checks"]
    if type(rows) is not list or len(rows) != len(CHECK_IDS):
        raise Problem("invalid_result")
    checks = []
    for check_id, row in zip(CHECK_IDS, rows):
        _object(row, ("id", "state", "reason", "source", "field"))
        if (row["id"] != check_id or row["state"] not in ("passed", "failed", "not_checked")
                or not isinstance(row["reason"], str) or row["reason"] not in REASONS
                or row["source"] not in (None, "project", "tasks")
                or (row["field"] is not None and (not isinstance(row["field"], str) or not FIELD.fullmatch(row["field"])))):
            raise Problem("invalid_result")
        if ((row["state"] == "passed") != (row["reason"] == "ok")
                or (row["state"] == "not_checked") != (row["reason"] in UNKNOWN_REASONS)):
            raise Problem("invalid_result")
        checks.append(Check(**row))
    by_id = {c.id: c for c in checks}
    if by_id["workspace_boundary"].state != "passed" or value["overall"] != aggregate(tuple(checks)):
        raise Problem("invalid_result")
    for alias, evidence in value["sources"].items():
        read, schema, fresh = (by_id[alias + "_" + name] for name in ("read", "schema", "freshness"))
        if (read.state == "passed") != (evidence is not None):
            raise Problem("invalid_result")
        if read.state != "passed" and schema.state != "not_checked":
            raise Problem("invalid_result")
        if schema.state == "passed":
            if evidence["as_of"] is None:
                raise Problem("invalid_result")
            expected = freshness(parse_time(evidence["as_of"]), start, alias)
            if (fresh.state, fresh.reason) != (expected.state, expected.reason):
                raise Problem("invalid_result")
        elif fresh.state != "not_checked" or (evidence is not None and evidence["as_of"] is not None):
            raise Problem("invalid_result")
    if any(by_id[a + "_schema"].state != "passed" for a in ("project", "tasks")):
        if by_id["project_identity"].state != "not_checked":
            raise Problem("invalid_result")
    if any(by_id[a + "_read"].state != "passed" for a in ("project", "tasks")):
        if by_id["source_stability"].state != "not_checked":
            raise Problem("invalid_result")
    prereqs = [c for c in checks if c.id != "brief_invariants"]
    if any(c.state != "passed" for c in prereqs) and by_id["brief_invariants"].state != "not_checked":
        raise Problem("invalid_result")
    if value["overall"] == "passed":
        validate_brief_shape(value["brief"])
        for alias in ("project", "tasks"):
            if value["brief"]["source_as_of"][alias] != value["sources"][alias]["as_of"]:
                raise Problem("invalid_result")
    elif value["brief"] is not None:
        raise Problem("invalid_result")
    return value


def validate_result(data: bytes, tool_version: str) -> JsonObject:
    try:
        return _validate_result(_decode(data, RESULT_LIMIT), tool_version)
    except Problem as exc:
        if exc.reason in ("too_large", "unsupported_result_version"):
            raise
        raise Problem("invalid_result") from None
    except (TypeError, ValueError, AttributeError, KeyError):
        raise Problem("invalid_result") from None

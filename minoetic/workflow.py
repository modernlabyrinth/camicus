"""One local observation, followed by explicit current verification."""
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from uuid import uuid4
from . import __version__, models
from .brief import build_brief, verify_brief
from .contracts import (CHECK_IDS, CONTRACT_VERSION, LIMITATIONS, RESULT_LIMIT,
                        RESULT_VERSION, SCOPE, SOURCE_LIMIT, aggregate, encode_result,
                        freshness, parse_project, parse_tasks, validate_result)
from .models import Check, Problem, stamp
from .storage import Workspace, valid_name


@dataclass(frozen=True)
class Outcome:
    exit_code: int
    overall: str
    checks: tuple[Check, ...]
    result_saved: bool


def checker_error(reason='internal_error'):
    return Outcome(3, 'checker_error', (Check('checker', 'failed', reason),), False)


def _skip(ident):
    return Check(ident, 'not_checked', 'dependency_unavailable')


def _ok(ident, source=None):
    return Check(ident, 'passed', 'ok', source)


def _problem(ident, exc, source=None):
    return Check(ident, exc.state, exc.reason, source, exc.field)


def _outcome(checks, saved=False):
    rows = tuple(checks)
    state = aggregate(rows)
    return Outcome({'passed': 0, 'failed': 1, 'not_checked': 2}[state], state, rows, saved)


def _workspace(path, checks):
    try:
        work = Workspace.open(path)
    except Problem as exc:
        checks['workspace_boundary'] = _problem('workspace_boundary', exc)
        return None
    checks['workspace_boundary'] = _ok('workspace_boundary')
    return work


def _observe(work, now, checks):
    snapshots, parsed = {}, {}
    for alias, parse in (('project', parse_project), ('tasks', parse_tasks)):
        try:
            snapshot = work.read(alias + '.json', SOURCE_LIMIT)
        except Problem as exc:
            checks[alias + '_read'] = _problem(alias + '_read', exc, alias)
            continue
        snapshots[alias] = snapshot
        checks[alias + '_read'] = _ok(alias + '_read', alias)
        try:
            parsed[alias] = parse(snapshot.data)
        except Problem as exc:
            checks[alias + '_schema'] = _problem(alias + '_schema', exc, alias)
            continue
        checks[alias + '_schema'] = _ok(alias + '_schema', alias)
        checks[alias + '_freshness'] = freshness(parsed[alias].as_of, now, alias)
    if len(parsed) == 2:
        checks['project_identity'] = (_ok('project_identity') if parsed['project'].project_id == parsed['tasks'].project_id
                                      else Check('project_identity', 'failed', 'project_mismatch'))
    return snapshots, parsed


def _ready(checks):
    return all(c.state == 'passed' for ident, c in checks.items()
               if ident not in ('source_stability', 'brief_invariants'))


def _stability(work, snapshots, checks):
    if len(snapshots) != 2:
        return
    observations = []
    for alias, snapshot in snapshots.items():
        try:
            work.unchanged(alias + '.json', snapshot, SOURCE_LIMIT)
        except Problem as exc:
            observations.append(_problem('source_stability', exc, alias))
    state = aggregate(tuple(observations)) if observations else 'passed'
    checks['source_stability'] = (next(c for c in observations if c.state == state)
                                  if observations else _ok('source_stability'))


def _run_check(path, filename, now):
    if not valid_name(filename, result=True):
        return checker_error('invalid_invocation')
    checks = {ident: _skip(ident) for ident in CHECK_IDS}
    work = _workspace(path, checks)
    if work is None:
        return _outcome(checks.values())
    with work:
        work.preflight_output(filename)
        snapshots, parsed = _observe(work, now, checks)
        brief = None
        if _ready(checks):
            brief = build_brief(parsed['project'], parsed['tasks'])
            checks['brief_invariants'] = verify_brief(brief, parsed['project'], parsed['tasks'])
        _stability(work, snapshots, checks)
        if checks['source_stability'].state != 'passed':
            checks['brief_invariants'] = _skip('brief_invariants')
        outcome = _outcome(checks.values())
        if outcome.overall != 'passed':
            brief = None
        sources = {}
        for alias in ('project', 'tasks'):
            snapshot = snapshots.get(alias)
            sources[alias] = (dict(sha256=sha256(snapshot.data).hexdigest(), byte_length=len(snapshot.data),
                                   as_of=stamp(parsed[alias].as_of) if alias in parsed else None,
                                   read_at=stamp(snapshot.read_at)) if snapshot is not None else None)
        result = dict(schema_version=RESULT_VERSION, tool_version=__version__, contract_version=CONTRACT_VERSION,
                      run_id=str(uuid4()), started_at=stamp(now), finished_at=stamp(models.utc_now()), scope=SCOPE,
                      sources=sources, checks=[asdict(c) for c in outcome.checks], overall=outcome.overall,
                      brief=brief, limitations=list(LIMITATIONS))
        data = encode_result(result)
        validate_result(data, __version__)
        work.publish(filename, data)
        return _outcome(checks.values(), saved=True)


def run_check(workspace: str, filename: str, now: datetime) -> Outcome:
    try:
        return _run_check(workspace, filename, now)
    except Problem as exc:
        return checker_error(exc.reason)
    except (Exception, KeyboardInterrupt):
        return checker_error()


def _binding(recorded, snapshots):
    missing = False
    for alias in ('project', 'tasks'):
        historical, current = recorded['sources'][alias], snapshots.get(alias)
        if historical is None:
            missing = True
        elif current is None:
            continue
        elif (historical['sha256'] != sha256(current.data).hexdigest()
              or historical['byte_length'] != len(current.data)):
            return Check('source_binding', 'failed', 'source_binding_mismatch', alias)
    if missing:
        return Check('source_binding', 'not_checked', 'historical_evidence_missing')
    if len(snapshots) != 2:
        return _skip('source_binding')
    return _ok('source_binding')


def _run_verify(path, filename, now):
    if not valid_name(filename, result=True):
        return checker_error('invalid_invocation')
    checks = {ident: _skip(ident) for ident in CHECK_IDS}
    extra = {ident: _skip(ident) for ident in ('result_read', 'result_schema', 'recorded_outcome', 'source_binding', 'result_stability')}
    work = _workspace(path, checks)
    if work is None:
        return _outcome((*checks.values(), *extra.values()))
    with work:
        try:
            saved = work.read(filename, RESULT_LIMIT)
        except Problem as exc:
            extra['result_read'] = _problem('result_read', exc)
            return _outcome((*checks.values(), *extra.values()))
        extra['result_read'] = _ok('result_read')
        try:
            recorded = validate_result(saved.data, __version__)
        except Problem as exc:
            extra['result_schema'] = _problem('result_schema', exc)
            return _outcome((*checks.values(), *extra.values()))
        extra['result_schema'] = _ok('result_schema')
        state = recorded['overall']
        extra['recorded_outcome'] = Check('recorded_outcome', state, {'passed': 'ok', 'failed': 'historical_failed', 'not_checked': 'historical_not_checked'}[state])
        snapshots, parsed = _observe(work, now, checks)
        extra['source_binding'] = _binding(recorded, snapshots)
        if _ready(checks) and recorded['brief'] is not None:
            checks['brief_invariants'] = verify_brief(recorded['brief'], parsed['project'], parsed['tasks'])
        _stability(work, snapshots, checks)
        if checks['source_stability'].state != 'passed':
            checks['brief_invariants'] = _skip('brief_invariants')
        try:
            work.unchanged(filename, saved, RESULT_LIMIT)
            extra['result_stability'] = _ok('result_stability')
        except Problem as exc:
            extra['result_stability'] = _problem('result_stability', exc)
        return _outcome((*checks.values(), *extra.values()))


def run_verify(workspace: str, filename: str, now: datetime) -> Outcome:
    try:
        return _run_verify(workspace, filename, now)
    except (Exception, KeyboardInterrupt):
        return checker_error()

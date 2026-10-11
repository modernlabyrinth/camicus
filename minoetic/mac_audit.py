"""Bounded, read-only observations of fixed macOS controls; no repair actions."""
from base64 import b64encode
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
import ipaddress
import os
import re
import selectors
import subprocess
import time
from uuid import uuid4
from . import __version__, models
from .models import Check, Problem, stamp
from .storage import Workspace, valid_name
from .workflow import Outcome, checker_error, _outcome

COMMANDS = (
    ('filevault', ('/usr/bin/fdesetup', 'status')),
    ('sip', ('/usr/bin/csrutil', 'status')),
    ('gatekeeper', ('/usr/sbin/spctl', '--status')),
    ('firewall', ('/usr/libexec/ApplicationFirewall/socketfilterfw', '--getglobalstate')),
    ('stealth', ('/usr/libexec/ApplicationFirewall/socketfilterfw', '--getstealthmode')),
    ('listeners', ('/usr/sbin/lsof', '-nP', '-iTCP', '-sTCP:LISTEN', '-Fpcn')),
)
OUTPUT_LIMIT = 128 * 1024
TIMEOUT = 5.0
ENV = {'LC_ALL': 'C', 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'}
LIMITATIONS = (
    'Only the listed controls at their observation times are checked.',
    'TCP listeners are a current-user visibility snapshot; process coverage may be incomplete.',
    'Listener observations do not establish internet reachability, malware absence, or device safety.',
    'Stealth mode is informational; disabled stealth is not a policy failure.',
    'Unsigned local evidence can be edited; rerun into a new file for current observations.',
)


@dataclass(frozen=True)
class Evidence:
    stdout: bytes
    stderr: bytes
    returncode: int | None
    reason: str | None = None


def collect(argv, *, timeout=TIMEOUT, limit=OUTPUT_LIMIT):
    """Keep at most limit total bytes, including stderr; kill and reap on limits."""
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    process = None
    reason = None
    deadline = time.monotonic() + timeout
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, shell=False, env=ENV,
                                   close_fds=True)
        with selectors.DefaultSelector() as selector:
            for name, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = 'timeout'
                    break
                for key, _ in selector.select(min(remaining, .1)):
                    available = limit - sum(map(len, buffers.values()))
                    chunk = os.read(key.fd, min(8192, available + 1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif len(chunk) > available:
                        buffers[key.data].extend(chunk[:available])
                        reason = 'output_limit'
                        break
                    else:
                        buffers[key.data].extend(chunk)
                if reason:
                    break
            if not reason:
                try:
                    process.wait(timeout=max(.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    reason = 'timeout'
    except FileNotFoundError:
        reason = 'command_missing'
    except PermissionError:
        reason = 'command_denied'
    except OSError:
        reason = 'command_unobserved'
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
            process.stderr.close()
    return Evidence(bytes(buffers['stdout']), bytes(buffers['stderr']),
                    process.returncode if process else None, reason)


POLICY = {
    'filevault': ('FileVault is On.', 'FileVault is Off.'),
    'sip': ('System Integrity Protection status: enabled.', 'System Integrity Protection status: disabled.'),
    'gatekeeper': ('assessments enabled', 'assessments disabled'),
    'firewall': ('Firewall is enabled. (State = 1)', 'Firewall is disabled. (State = 0)'),
    'stealth': ('Stealth mode enabled', 'Stealth mode disabled'),
}


def finding(ident, evidence):
    def unknown(reason):
        return Check(ident, 'not_checked', reason), None
    if evidence.reason:
        return unknown(evidence.reason)
    if evidence.returncode != 0:
        return unknown('command_failed')
    if evidence.stderr:
        return unknown('unexpected_stderr')
    try:
        text = evidence.stdout.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        return unknown('unrecognized_output')
    if ident in POLICY:
        choices = POLICY[ident]
        if text.strip() not in choices:
            return unknown('unrecognized_output')
        enabled = text.strip() == choices[0]
        return Check(ident, 'passed' if enabled or ident == 'stealth' else 'failed',
                     'observed' if ident == 'stealth' else 'enabled' if enabled else 'disabled'), enabled
    # A zero-exit empty lsof response is ambiguous. Reject partial records and
    # unterminated output instead of interpreting it as a clean empty snapshot.
    if not text or not text.endswith('\n'):
        return unknown('unrecognized_output')
    rows, pid, command, fd = [], None, None, None
    seen_pids, seen_fds = set(), set()
    process_complete, fd_complete = False, False
    # lsof includes the mandatory file descriptor field even with -Fpcn.
    # Require each process to own complete file records, each with one endpoint.
    for line in text[:-1].split('\n'):
        if not line or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in line):
            return unknown('unrecognized_output')
        if re.fullmatch(r'p[1-9][0-9]*', line):
            if pid is not None and not (process_complete and fd_complete):
                return unknown('unrecognized_output')
            pid = int(line[1:])
            if pid in seen_pids:
                return unknown('unrecognized_output')
            seen_pids.add(pid)
            command, fd = None, None
            seen_fds = set()
            process_complete, fd_complete = False, False
        elif line.startswith('c') and len(line) > 1 and pid is not None and command is None and fd is None:
            command = line[1:]
        elif re.fullmatch(r'f[0-9]+', line) and command is not None:
            if fd is not None and not fd_complete:
                return unknown('unrecognized_output')
            fd = line[1:]
            if fd in seen_fds:
                return unknown('unrecognized_output')
            seen_fds.add(fd)
            fd_complete = False
        elif line.startswith('n') and fd is not None and not fd_complete:
            endpoint = line[1:]
            match = re.fullmatch(r'(\*|[0-9.]+|\[[0-9A-Fa-f:.%a-zA-Z0-9_-]+\]):([0-9]{1,5})', endpoint)
            if match is None or not 1 <= int(match[2]) <= 65535:
                return unknown('unrecognized_output')
            host = match[1]
            if host != '*':
                try:
                    address = ipaddress.ip_address(host[1:-1] if host.startswith('[') else host)
                    if host.startswith('[') != (address.version == 6):
                        return unknown('unrecognized_output')
                except ValueError:
                    return unknown('unrecognized_output')
            rows.append(dict(pid=pid, command=command, fd=fd, endpoint=endpoint))
            process_complete, fd_complete = True, True
        else:
            return unknown('unrecognized_output')
    if not rows or not (process_complete and fd_complete):
        return unknown('unrecognized_output')
    return Check(ident, 'passed', 'snapshot_collected'), rows


def run_audit(path: str, filename: str, now: datetime) -> Outcome:
    try:
        if not valid_name(filename, result=True):
            return checker_error('invalid_invocation')
        try:
            work = Workspace.open(path)
        except Problem as exc:
            return _outcome((Check('workspace_boundary', exc.state, exc.reason),))
        with work:
            work.preflight_output(filename)
            checks = [Check('workspace_boundary', 'passed', 'ok')]
            evidence, findings = {}, {}
            for ident, argv in COMMANDS:
                observed_at = stamp(models.utc_now())
                raw = collect(argv)
                check, value = finding(ident, raw)
                checks.append(check)
                findings[ident] = value
                evidence[ident] = dict(argv=list(argv), observed_at=observed_at,
                    returncode=raw.returncode, reason=raw.reason,
                    stdout_base64=b64encode(raw.stdout).decode('ascii'),
                    stderr_base64=b64encode(raw.stderr).decode('ascii'),
                    stdout_sha256=sha256(raw.stdout).hexdigest(),
                    stderr_sha256=sha256(raw.stderr).hexdigest(),
                    stdout_bytes=len(raw.stdout), stderr_bytes=len(raw.stderr))
            outcome = _outcome(checks)
            result = dict(schema_version='minoetic.mac-audit/1', tool_version=__version__,
                          run_id=str(uuid4()), started_at=stamp(now), finished_at=stamp(models.utc_now()),
                          scope='fixed-read-only-mac-controls', checks=[asdict(c) for c in checks],
                          overall=outcome.overall, findings=findings, evidence=evidence,
                          limits=dict(command_seconds=TIMEOUT, command_output_bytes=OUTPUT_LIMIT),
                          limitations=list(LIMITATIONS))
            work.publish(filename, (json.dumps(result, ensure_ascii=True, separators=(',', ':')) + '\n').encode())
            return _outcome(checks, saved=True)
    except Problem as exc:
        return checker_error(exc.reason)
    except (Exception, KeyboardInterrupt):
        return checker_error()

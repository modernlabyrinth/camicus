"""Fixed diagnostics: arguments and exception text are never echoed."""
from dataclasses import asdict
import json
import os
import sys
from . import __version__, models
from .storage import acl_available, valid_name
from .workflow import Outcome, checker_error, run_check, run_verify

HELP = '''Minoetic — Check what still works.
check --workspace ABSOLUTE_PATH --output NEW_NAME.json
verify --workspace ABSOLUTE_PATH --result SAVED_NAME.json
--help | --version
Local weekly-brief checks only; results are private, unsigned evidence.'''


def format_outcome(outcome: Outcome) -> str:
    return json.dumps(dict(overall=outcome.overall, exit_code=outcome.exit_code,
                           result_saved=outcome.result_saved,
                           checks=[asdict(c) for c in outcome.checks]), separators=(',', ':'))


def _supported():
    if sys.platform != 'darwin' or not (3, 11) <= sys.version_info[:2] <= (3, 14):
        return False
    if int(os.uname().release.split('.')[0]) < 23:
        return False
    return (acl_available() and all(hasattr(os, flag) for flag in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_NONBLOCK'))
            and all(fn in os.supports_dir_fd for fn in (os.open, os.stat, os.link, os.unlink))
            and os.stat in os.supports_follow_symlinks and os.link in os.supports_follow_symlinks)


def _arguments(argv):
    if len(argv) != 5 or argv[0] not in ('check', 'verify'):
        return None
    file_flag = '--output' if argv[0] == 'check' else '--result'
    pairs = list(zip(argv[1::2], argv[2::2]))
    if {key for key, _ in pairs} != {'--workspace', file_flag}:
        return None
    values = dict(pairs)
    path, filename = values['--workspace'], values[file_flag]
    if (not path.startswith('/') or '..' in path.split('/') or '\x00' in path
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in path)
            or not valid_name(filename, result=True)):
        return None
    return argv[0], path, filename


def main(argv: list[str] | None = None) -> int:
    try:
        args = sys.argv[1:] if argv is None else argv
        if args == ['--help']:
            print(HELP)
            return 0
        if args == ['--version']:
            print('minoetic ' + __version__)
            return 0
        selected = _arguments(args)
        if selected is None:
            outcome = checker_error('invalid_invocation')
        elif not _supported():
            outcome = checker_error('unsupported_platform')
        else:
            command, workspace, filename = selected
            run = run_check if command == 'check' else run_verify
            outcome = run(workspace, filename, models.utc_now())
    except (Exception, KeyboardInterrupt):
        outcome = checker_error()
    print(format_outcome(outcome))
    return outcome.exit_code

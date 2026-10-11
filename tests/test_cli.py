import ast
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch
from tests.support import ModulesCase, NOW, project_bytes, tasks_bytes

SENTINEL = 'SECRET_SENTINEL_7c91'


class CliTests(ModulesCase):
    def setUp(self):
        self.cli = self.module('cli')
        self.root = self.workspace()

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.cli.main(args)
        self.assertEqual(err.getvalue(), '')
        self.assertNotIn(SENTINEL, out.getvalue())
        self.assertNotIn(str(self.root), out.getvalue())
        return code, out.getvalue()

    def test_argument_error_is_private(self):
        base = ['check', '--workspace', str(self.root), '--output', 'new.json']
        cases = [[], ['check'], base + ['--' + SENTINEL], base + [SENTINEL],
                 base + ['--output', 'duplicate.json'], base + ['--result', 'extra.json'],
                 ['check', '--workspace', SENTINEL, '--output', 'a.json']]
        for name in ('../' + SENTINEL + '.json', 'bad\n.json', 'project.json', 'tasks.json', 'PROJECT.json', 'TASKS.json', 'Taſks.json', 'not-json'):
            cases.append(base[:-1] + [name])
        for args in cases:
            with patch.object(self.module('storage').Workspace, 'open') as opened:
                code, text = self.invoke(args)
                self.assertEqual(code, 3)
                self.assertEqual(json.loads(text)['checks'][0]['reason'], 'invalid_invocation')
                opened.assert_not_called()

    def test_case_alias_result_argument_rejected_before_reads(self):
        for name in ('PROJECT.json', 'TASKS.json'):
            with patch.object(self.module('storage').Workspace, 'open') as opened:
                self.assertEqual(self.invoke(['verify', '--workspace', str(self.root), '--result', name])[0], 3)
                opened.assert_not_called()

    def test_mac_audit_arguments_keep_explicit_private_output_boundary(self):
        args = ['audit-mac', '--workspace', str(self.root), '--output', 'audit.json']
        self.assertEqual(self.cli._arguments(args), ('audit-mac', str(self.root), 'audit.json'))
        for name in ('../escape.json', 'project.json', 'TASKS.json', 'bad\n.json'):
            self.assertIsNone(self.cli._arguments(args[:-1] + [name]))
        self.assertIsNone(self.cli._arguments(args[:-2] + ['--result', 'audit.json']))

    def test_mac_audit_routes_to_separate_contract(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        audit = Mock(return_value=self.module('workflow').Outcome(2, 'not_checked', (), True))
        with patch.dict(sys.modules, {'minoetic.mac_audit': SimpleNamespace(run_audit=audit)}):
            code, text = self.invoke(['audit-mac', '--workspace', str(self.root), '--output', 'audit.json'])
        self.assertEqual(code, 2)
        self.assertTrue(json.loads(text)['result_saved'])
        self.assertEqual(audit.call_args.args[:2], (str(self.root), 'audit.json'))

    def test_exception_is_private(self):
        for error in (OSError(SENTINEL), RuntimeError(SENTINEL), KeyboardInterrupt(SENTINEL)):
            with patch.object(self.cli, 'run_check', side_effect=error):
                code, text = self.invoke(['check', '--workspace', str(self.root), '--output', 'out.json'])
            self.assertEqual(code, 3)
            self.assertEqual(json.loads(text)['overall'], 'checker_error')

    def test_help_version_and_platform(self):
        for args in (['--help'], ['--version']):
            self.assertEqual(self.invoke(args)[0], 0)
        for attribute, value in (('platform', 'win32'), ('version_info', (3, 10, 0)), ('version_info', (3, 15, 0))):
            with patch.object(self.cli.sys, attribute, value):
                code, text = self.invoke(['check', '--workspace', str(self.root), '--output', 'out.json'])
            self.assertEqual(code, 3)
            self.assertEqual(json.loads(text)['checks'][0]['reason'], 'unsupported_platform')

    def test_missing_native_acl_api_is_unsupported_before_reads(self):
        with patch('minoetic.storage._ACL_API', None), patch.object(self.module('storage').Workspace, 'open') as opened:
            code, text = self.invoke(['check', '--workspace', str(self.root), '--output', 'out.json'])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(text)['checks'][0]['reason'], 'unsupported_platform')
        opened.assert_not_called()

    def test_success_diagnostics_omit_source_content(self):
        (self.root / 'project.json').write_bytes(project_bytes(summary=SENTINEL))
        (self.root / 'tasks.json').write_bytes(tasks_bytes([dict(id=SENTINEL, title=SENTINEL, state='blocked')]))
        with patch('minoetic.models.utc_now', return_value=NOW):
            code, text = self.invoke(['check', '--workspace', str(self.root), '--output', 'out.json'])
        self.assertEqual(code, 0)
        value = json.loads(text)
        self.assertEqual(set(value), {'overall', 'exit_code', 'result_saved', 'checks'})
        self.assertTrue(all(set(c) == {'id', 'state', 'reason', 'source', 'field'} for c in value['checks']))
        self.assertNotIn('sha256', text)

    def test_weekly_runtime_has_no_network_or_process_operations(self):
        events = []
        enabled = [True]
        def observer(event, _args):
            if enabled[0] and (event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'os.fork')):
                events.append(event)
                raise AssertionError(event)
        sys.addaudithook(observer)
        try:
            (self.root / 'project.json').write_bytes(project_bytes())
            (self.root / 'tasks.json').write_bytes(tasks_bytes())
            with patch('minoetic.models.utc_now', return_value=NOW):
                self.assertEqual(self.invoke(['check', '--workspace', str(self.root), '--output', 'out.json'])[0], 0)
                self.assertEqual(self.invoke(['verify', '--workspace', str(self.root), '--result', 'out.json'])[0], 0)
        finally:
            enabled[0] = False
        self.assertEqual(events, [])
        package = Path(__file__).parents[1] / 'minoetic'
        for path in package.glob('*.py'):
            forbidden = {'socket', 'urllib', 'http', 'requests', 'glob'}
            if path.name not in ('mac_audit.py', 'mac_probe.py'):
                forbidden.add('subprocess')
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({a.name.split('.')[0] for a in node.names} & forbidden)
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], forbidden)
                if isinstance(node, ast.Call):
                    name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
                    self.assertNotIn(name, {'eval', 'exec', 'walk', 'rglob', 'listdir', 'scandir', 'system', 'popen'})

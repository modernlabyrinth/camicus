import hashlib
import json
import os
import sys
from unittest.mock import patch
from tests.support import ModulesCase, NOW


class MacAuditTests(ModulesCase):
    def setUp(self):
        self.audit = self.module('mac_audit')

    def evidence(self, data=b'FileVault is On.\n', reason=None, code=0):
        return self.audit.Evidence(data, b'', code, reason)

    def test_policy_parsers(self):
        for ident, enabled, disabled in (
            ('filevault', 'FileVault is On.', 'FileVault is Off.'),
            ('sip', 'System Integrity Protection status: enabled.', 'System Integrity Protection status: disabled.'),
            ('gatekeeper', 'assessments enabled', 'assessments disabled'),
            ('firewall', 'Firewall is enabled. (State = 1)', 'Firewall is disabled. (State = 0)')):
            self.assertEqual(self.audit.finding(ident, self.evidence(enabled.encode()))[0].state, 'passed')
            self.assertEqual(self.audit.finding(ident, self.evidence(disabled.encode()))[0].state, 'failed')
            for ev in (self.evidence(b'unknown'), self.evidence(reason='timeout'), self.evidence(code=1)):
                self.assertEqual(self.audit.finding(ident, ev)[0].state, 'not_checked')

    def test_stealth_informational_and_listeners(self):
        check, value = self.audit.finding('stealth', self.evidence(b'Stealth mode disabled'))
        self.assertEqual((check.state, value), ('passed', False))
        for data in (b'', b'p123\ncfixture\nf4\nn*:9000', b'p123\ncfixture\nf4\nn*:9000\ntruncated\n'):
            self.assertEqual(self.audit.finding('listeners', self.evidence(data))[0].state, 'not_checked')
        check, value = self.audit.finding('listeners', self.evidence(b'p123\ncfixture\nf4\nn*:9000\n'))
        self.assertEqual(check.reason, 'snapshot_collected')
        self.assertEqual(value[0]['endpoint'], '*:9000')

    def test_bounded_runner(self):
        for script, reason in (('import time; time.sleep(2)', 'timeout'),
                               ('import os; os.write(1,b"x"*100000)', 'output_limit'),
                               ('import os; os.write(2,b"x"*100000)', 'output_limit')):
            ev = self.audit.collect((sys.executable, '-c', script), timeout=.1, limit=100)
            self.assertEqual(ev.reason, reason)
            self.assertLessEqual(len(ev.stdout) + len(ev.stderr), 100)
        with patch.object(self.audit.subprocess, 'Popen', side_effect=PermissionError):
            self.assertEqual(self.audit.collect(('/fake',)).reason, 'command_denied')

    def test_missing_and_stderr(self):
        self.assertEqual(self.audit.collect(('/nonexistent-minoetic-fixture',)).reason, 'command_missing')
        raw = self.audit.Evidence(b'FileVault is On.\n', b'denied', 0)
        self.assertEqual(self.audit.finding('filevault', raw)[0].state, 'not_checked')
        raw = self.evidence(b'FileVault is On.\n', reason='output_limit')
        self.assertEqual(self.audit.finding('filevault', raw)[0].state, 'not_checked')

    def test_preflight_private_publication(self):
        root = self.workspace()
        fixtures = [b'FileVault is On.\n', b'System Integrity Protection status: enabled.\n',
                    b'assessments enabled\n', b'Firewall is enabled. (State = 1)\n',
                    b'Stealth mode disabled\n', b'p123\ncfixture\nf4\nn127.0.0.1:9000\n']
        with patch('minoetic.storage._has_extended_acl', return_value=False), patch.object(self.audit, 'collect', side_effect=[self.evidence(x) for x in fixtures]) as probe:
            result = self.audit.run_audit(str(root), 'audit.json', NOW)
            self.assertTrue(result.result_saved)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(probe.call_count, 6)
            saved = json.loads((root / 'audit.json').read_bytes())
            self.assertEqual(saved['schema_version'], 'minoetic.mac-audit/1')
            self.assertEqual(saved['evidence']['filevault']['stdout_sha256'], hashlib.sha256(fixtures[0]).hexdigest())
            self.assertEqual((root / 'audit.json').stat().st_mode & 0o777, 0o600)
        with patch('minoetic.storage._has_extended_acl', return_value=False), patch.object(self.audit, 'collect') as probe:
            result = self.audit.run_audit(str(root), 'audit.json', NOW)
            self.assertEqual(result.checks[0].reason, 'output_conflict')
            probe.assert_not_called()

    def test_actual_lsof_fields_and_reject_incomplete_records(self):
        good = b'p123\ncfixture\nf4\nn127.0.0.1:9000\nf5\nn[::1]:9000\np456\ncother\nf9\nn*:443\n'
        check, rows = self.audit.finding('listeners', self.evidence(good))
        self.assertEqual(check.state, 'passed')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['fd'], '4')
        for data in (b'', b'p123\ncfixture\nf4\n',
                     good + b'p456\ncother\n',
                     b'p123\ncfixture\nf4\nnnot-an-endpoint\n',
                     b'p123\ncfixture\nf4\nn*:65536\n',
                     b'p123\ncfixture\nf4\nn*:0\n',
                     b'p123\ncfixture\nf4\nn127.0.0.1:abc\n',
                     b'p123\ncfixture\nf4\nn[invalid]:80\n',
                     b'p123\ncfixture\nf4\nn*:80\nxunexpected\n',
                     b'p123\ncfixture\nf4\nn*:80\nn*:81\n',
                     b'p123\ncfixture\nf4\nn*:80\np123\ncfixture\n',
                     b'p123\ncfix\x01ture\nf4\nn*:80\n',
                     b'p123\ncfix\nture\nf4\nn*:80\n',
                     b'p123\ncfixture\nf4\nn*:80\rf5\n'):
            with self.subTest(data=data):
                self.assertEqual(self.audit.finding('listeners', self.evidence(data))[0].state, 'not_checked')
        self.assertEqual(self.audit.finding('listeners', self.evidence(b'', code=1))[0].state, 'not_checked')

import copy
from datetime import timedelta
import hashlib
import json
import os
from unittest.mock import patch
from tests.support import ModulesCase, NOW, STAMP, IDS, dump, project_bytes, tasks_bytes, valid_result


class WorkflowTests(ModulesCase):
    def setUp(self):
        self.flow = self.module('workflow')
        self.storage = self.module('storage')
        self.root = self.workspace()
        (self.root / 'project.json').write_bytes(project_bytes())
        (self.root / 'tasks.json').write_bytes(tasks_bytes())
        clock = patch('minoetic.models.utc_now', return_value=NOW)
        clock.start(); self.addCleanup(clock.stop)

    def check(self, name='result.json'):
        return self.flow.run_check(str(self.root), name, NOW)

    def verify(self, name='result.json', now=NOW):
        with patch.object(self.storage.Workspace, 'publish', side_effect=AssertionError('verify wrote')):
            return self.flow.run_verify(str(self.root), name, now)

    def receipt(self, name='result.json'):
        return json.loads((self.root / name).read_bytes())

    def test_check_then_verify(self):
        outcome = self.check()
        self.assertEqual((outcome.exit_code, outcome.overall, outcome.result_saved), (0, 'passed', True))
        receipt = self.receipt()
        self.assertEqual(receipt['brief'], valid_result()['brief'])
        self.assertEqual([c['id'] for c in receipt['checks']], list(IDS))
        self.assertEqual(receipt['sources']['project']['sha256'], hashlib.sha256(project_bytes()).hexdigest())
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()}
        self.assertEqual(self.verify().exit_code, 0)
        after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()}
        self.assertEqual(before, after)

    def test_shared_clock_observations(self):
        self.assertEqual(self.check().exit_code, 0)
        receipt = self.receipt()
        self.assertEqual(receipt['started_at'], STAMP)
        self.assertEqual(receipt['finished_at'], STAMP)
        self.assertTrue(all(s['read_at'] == STAMP for s in receipt['sources'].values()))
        ticks = iter(NOW + timedelta(seconds=i) for i in range(1, 20))
        with patch('minoetic.models.utc_now', side_effect=lambda: next(ticks)):
            self.assertEqual(self.check('advancing.json').exit_code, 0)
        receipt = self.receipt('advancing.json')
        self.assertLess(receipt['started_at'], receipt['sources']['project']['read_at'])
        self.assertLess(receipt['sources']['tasks']['read_at'], receipt['finished_at'])

    def test_missing_malformed_stale_mismatch(self):
        for index, data in enumerate((None, b'{', tasks_bytes(as_of='2026-10-01T00:00:00Z'), tasks_bytes(project_id='other'))):
            with self.subTest(data=data):
                path = self.root / 'tasks.json'
                if data is None:
                    path.unlink()
                else:
                    path.write_bytes(data)
                name = f'failure-{index}.json'
                self.assertEqual(self.check(name).exit_code, 1)
                receipt = self.receipt(name)
                self.assertIsNone(receipt['brief'])
                self.assertEqual(receipt['checks'][8]['state'], 'not_checked')

    def deny(self, missing=False):
        original = self.storage.Workspace.read
        if missing:
            (self.root / 'project.json').unlink()
        def read(work, name, limit):
            if name == 'tasks.json':
                raise self.module('models').Problem('read_denied', 'not_checked')
            return original(work, name, limit)
        return patch.object(self.storage.Workspace, 'read', read)

    def test_permission_denied(self):
        with self.deny():
            self.assertEqual(self.check().exit_code, 2)
        self.assertIsNone(self.receipt()['sources']['tasks'])
        self.assertIsNone(self.receipt()['brief'])

    def test_failure_precedence(self):
        with self.deny(missing=True):
            self.assertEqual(self.check().exit_code, 1)

    def test_unsafe_workspace_no_publication(self):
        self.root.chmod(0o770)
        with patch.object(self.storage.Workspace, 'publish') as publish:
            self.assertEqual(self.check().exit_code, 1)
            publish.assert_not_called()
        with patch.object(self.storage.Workspace, 'open', side_effect=self.module('models').Problem('read_denied', 'not_checked')), patch.object(self.storage.Workspace, 'publish') as publish:
            self.assertEqual(self.check().exit_code, 2)
            publish.assert_not_called()

    def test_output_conflict_precedes_source_reads(self):
        (self.root / 'result.json').write_bytes(b'keep')
        with patch.object(self.storage.Workspace, 'read') as read:
            self.assertEqual(self.check().exit_code, 3)
            read.assert_not_called()
        self.assertEqual((self.root / 'result.json').read_bytes(), b'keep')

    def test_tampered_result(self):
        self.assertEqual(self.check().exit_code, 0)
        good = self.receipt()
        mutations = [
            lambda r: r['brief']['task_counts'].update(todo=2),
            lambda r: r['brief']['blocked_tasks'].clear(),
            lambda r: r['brief'].update(project_summary='invented'),
            lambda r: r['sources']['tasks'].update(sha256='0' * 64),
            lambda r: r['checks'].append(dict(id='invented')),
        ]
        for mutation in mutations:
            value = copy.deepcopy(good); mutation(value)
            (self.root / 'result.json').write_bytes(dump(value))
            self.assertEqual(self.verify().exit_code, 1)

    def test_historical_failure_cannot_pass(self):
        (self.root / 'tasks.json').unlink()
        self.assertEqual(self.check().exit_code, 1)
        (self.root / 'tasks.json').write_bytes(tasks_bytes())
        outcome = self.verify()
        self.assertEqual(outcome.exit_code, 1)
        self.assertIn('historical_evidence_missing', [c.reason for c in outcome.checks])
        self.assertIn('historical_failed', [c.reason for c in outcome.checks])

    def test_historical_unknown_cannot_pass(self):
        with self.deny():
            self.assertEqual(self.check().exit_code, 2)
        self.assertEqual(self.verify().exit_code, 2)
        (self.root / 'project.json').write_bytes(project_bytes(summary='different'))
        self.assertEqual(self.verify().exit_code, 1)

    def test_verification_expires(self):
        self.check()
        self.assertEqual(self.verify(now=NOW + timedelta(days=8)).exit_code, 1)

    def test_late_stability_invalidates_brief(self):
        original = self.storage.Workspace.unchanged
        for alias in ('project', 'tasks'):
            for state, reason, code in (('failed', 'source_changed', 1), ('not_checked', 'source_unobserved', 2)):
                def changed(work, name, snapshot, limit):
                    if name == alias + '.json':
                        raise self.module('models').Problem(reason, state)
                    return original(work, name, snapshot, limit)
                name = f'{alias}-{code}.json'
                with patch.object(self.storage.Workspace, 'unchanged', changed):
                    self.assertEqual(self.check(name).exit_code, code)
                self.assertIsNone(self.receipt(name)['brief'])
                self.assertEqual(self.receipt(name)['checks'][8]['state'], 'not_checked')

    def test_saved_result_changed_during_verify(self):
        self.check()
        original = self.storage.Workspace.unchanged
        def changed(work, name, snapshot, limit):
            if name == 'result.json':
                raise self.module('models').Problem('source_changed')
            return original(work, name, snapshot, limit)
        with patch.object(self.storage.Workspace, 'unchanged', changed):
            outcome = self.verify()
        self.assertEqual(outcome.exit_code, 1)
        self.assertIn('result_stability', [c.id for c in outcome.checks if c.state == 'failed'])

    def test_publication_fault_never_success(self):
        original = self.storage.Workspace.publish
        def post_link(work, name, data):
            original(work, name, data)
            raise self.module('models').Problem('publication_failed')
        with patch.object(self.storage.Workspace, 'publish', post_link):
            outcome = self.check()
        self.assertEqual((outcome.exit_code, outcome.overall, outcome.result_saved), (3, 'checker_error', False))
        self.assertIsNotNone(self.receipt()['brief'])
        before = (self.root / 'result.json').read_bytes()
        self.assertEqual(self.check().exit_code, 3)
        self.assertEqual((self.root / 'result.json').read_bytes(), before)

    def test_serialization_failure_no_publication(self):
        with patch.object(self.flow, 'encode_result', side_effect=ValueError('private')), patch.object(self.storage.Workspace, 'publish') as publish:
            self.assertEqual(self.check().exit_code, 3)
            publish.assert_not_called()

    def test_maximum_unicode_end_to_end(self):
        (self.root / 'project.json').write_bytes(project_bytes(summary='😀' * 2000))
        (self.root / 'tasks.json').write_bytes(tasks_bytes([dict(id=f't{i}', title='😀' * 240, state='blocked') for i in range(1000)]))
        self.assertEqual(self.check().exit_code, 0)
        self.assertEqual(self.verify().exit_code, 0)
        self.assertEqual(len(self.receipt()['brief']['blocked_tasks']), 1000)

    def test_missing_source_case_alias_never_written(self):
        for name, restore in (('project', project_bytes), ('tasks', tasks_bytes)):
            source = self.root / (name + '.json'); source.unlink()
            outcome = self.check(name.upper() + '.json')
            self.assertEqual(outcome.exit_code, 3)
            self.assertFalse(source.exists())
            self.assertFalse((self.root / (name.upper() + '.json')).exists())
            source.write_bytes(restore())

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from tools.build_plugin import build_plugin, SOURCE_FILES

ROOT = Path(__file__).resolve().parents[1]

class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
    def tearDown(self):
        self.temp.cleanup()
    def test_allowlist_digest_determinism_relocation_and_execution(self):
        source = self.base / 'source'
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        (source / 'plugin-source' / 'sentinel-secret').write_text('DO NOT SHIP')
        first, second = self.base / 'first', self.base / 'second'
        build_plugin(source, first)
        build_plugin(source, second)
        expected = set(SOURCE_FILES) | {'bin/camicus', 'bin/camicus.sha256', 'LICENSE', 'INSTALL.md'}
        actual = {str(p.relative_to(first)) for p in first.rglob('*') if p.is_file()}
        self.assertEqual(actual, expected)
        for name in actual:
            self.assertEqual((first/name).read_bytes(), (second/name).read_bytes())
        digest = hashlib.sha256((first/'bin/camicus').read_bytes()).hexdigest()
        self.assertEqual((first/'bin/camicus.sha256').read_text(), digest+'  camicus\n')
        relocated = self.base / 'moved package'
        first.rename(relocated)
        shutil.rmtree(source)
        result = subprocess.run([sys.executable, '-I', '-S', str(relocated/'bin/camicus'), '--help'], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'audit-mac', result.stdout)
        for name in ('weekly-brief', 'mac-audit'):
            content = (relocated/'skills'/name/'SKILL.md').read_text()
            self.assertIn(digest, content)
            self.assertNotIn('/Users/', content)
    def test_existing_and_relative_destination_refused(self):
        destination = self.base/'exists'
        destination.mkdir()
        with self.assertRaises(FileExistsError): build_plugin(ROOT, destination)
        with self.assertRaises(ValueError): build_plugin(ROOT, Path('relative'))
        self.assertEqual(list(destination.iterdir()), [])
    def test_malformed_and_symlink_source_leave_no_partial_output(self):
        source = self.base/'source'
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        manifest = source/'plugin-source/plugin.json'
        manifest.write_text('{bad')
        destination = self.base/'output'
        with self.assertRaises(ValueError): build_plugin(source, destination)
        self.assertFalse(destination.exists())
        manifest.unlink()
        manifest.symlink_to(ROOT/'plugin-source/plugin.json')
        with self.assertRaises(ValueError): build_plugin(source, destination)
        self.assertFalse(destination.exists())
    def test_symlink_destination_parent_refused(self):
        parent = self.base/'alias'
        parent.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError): build_plugin(ROOT, parent/'output')
    def test_racing_destination_not_replaced_and_stage_cleaned(self):
        from unittest.mock import patch
        from tools import build_plugin as module
        original = module._publish
        destination = self.base/'race'
        def race(stage, output, descriptor):
            output.mkdir()
            (output/'owned').write_text('preserve')
            return original(stage, output, descriptor)
        with patch.object(module, '_publish', race):
            with self.assertRaises(OSError): build_plugin(ROOT, destination)
        self.assertEqual((destination/'owned').read_text(), 'preserve')
        self.assertFalse(list(self.base.glob('.camicus-stage-*')))
    def test_bad_skill_placeholder_cleans_staged_package(self):
        source=self.base/'source'
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns('.git','__pycache__'))
        skill=source/'plugin-source/skills/mac-audit/SKILL.md'
        skill.write_text(skill.read_text().replace('@ARCHIVE_SHA256@','bad'))
        output=self.base/'output'
        with self.assertRaises(ValueError): build_plugin(source, output)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.base.glob('.camicus-stage-*')))
    def test_isolated_builder_from_hostile_working_directory(self):
        hostile = self.base/'hostile'
        hostile.mkdir()
        sentinel = hostile/'executed'
        attack = "from pathlib import Path\nPath("+repr(str(sentinel))+").write_text('bad')\nraise RuntimeError('hostile module loaded')\n"
        (hostile/'json.py').write_text(attack)
        (hostile/'sitecustomize.py').write_text(attack)
        output = self.base/'isolated-output'
        result = subprocess.run([sys.executable, '-I', '-S', str(ROOT/'tools/build_plugin.py'),
                                 '--output', str(output)], cwd=hostile, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((output/'bin/camicus').is_file())
        self.assertFalse(sentinel.exists())
    def test_racing_source_symlink_never_read(self):
        from unittest.mock import patch
        from tools import build_plugin as module
        import os
        source = self.base/'source'
        source.mkdir()
        allowed = source/'allowed'
        allowed.write_text('allowed')
        secret = self.base/'secret'
        secret.write_text('private fixture must never ship')
        original = os.open
        def swap(path, flags, *args, **kwargs):
            if path == 'allowed':
                allowed.unlink()
                allowed.symlink_to(secret)
            return original(path, flags, *args, **kwargs)
        with patch.object(module.os, 'open', swap):
            with self.assertRaises(ValueError): module._regular(source, 'allowed')
    def test_mutating_source_during_read_refused(self):
        from unittest.mock import patch
        from tools import build_plugin as module
        import os
        source = self.base/'source'
        source.mkdir()
        allowed = source/'allowed'
        allowed.write_text('allowed')
        original = os.read
        mutated = False
        def mutate(descriptor, size):
            nonlocal mutated
            result = original(descriptor, size)
            if not mutated:
                mutated = True
                allowed.write_text('changed contents')
            return result
        with patch.object(module.os, 'read', mutate):
            with self.assertRaises(ValueError): module._regular(source, 'allowed')

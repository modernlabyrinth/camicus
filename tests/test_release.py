from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile
from tests.support import ModulesCase

ROOT = Path(__file__).parents[1]
RUNTIME = {'minoetic/' + name + '.py' for name in ('__init__', '__main__', 'models', 'contracts', 'brief', 'storage', 'workflow', 'cli')}


class ReleaseTests(ModulesCase):
    def tool(self, name):
        path = ROOT / 'tools' / (name + '.py')
        self.assertTrue(path.is_file(), 'Required release tool not implemented: ' + name)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def setUp(self):
        self.builder = self.tool('build_release')
        self.demo = self.tool('make_demo')
        self.root = self.workspace()

    def build(self, name='minoetic'):
        archive = self.root / name
        digest = self.builder.build_archive(ROOT, archive)
        self.assertEqual(digest, hashlib.sha256(archive.read_bytes()).hexdigest())
        return archive

    def call(self, archive, *args, cwd=None, direct=False):
        command = [str(archive)] if direct else [sys.executable, '-I', '-S', str(archive)]
        result = subprocess.run(command + list(args), cwd=cwd or self.root, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.stderr, '')
        return result.returncode, result.stdout

    def test_archive_allowlist(self):
        source = self.root / 'source'; source.mkdir()
        shutil.copytree(ROOT / 'minoetic', source / 'minoetic')
        (source / '.secret-ignored').write_text('SECRET_SENTINEL_7c91')
        (source / 'minoetic' / 'unexpected.py').write_text('SECRET_SENTINEL_7c91')
        (source / 'LICENSE').write_text('fictional license fixture')
        archive = self.root / 'candidate'
        self.builder.build_archive(source, archive)
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(set(package.namelist()), RUNTIME | {'__main__.py', 'LICENSE'})
            self.assertFalse(any(b'SECRET_SENTINEL_7c91' in package.read(name) for name in package.namelist()))

    def test_archive_is_deterministic(self):
        first, second = self.build('first'), self.build('second')
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o700)
        with self.assertRaises(FileExistsError):
            self.builder.build_archive(ROOT, first)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_archive_isolated_from_cwd(self):
        archive = self.build()
        hostile = self.root / 'hostile'; hostile.mkdir()
        marker = hostile / 'executed'
        payload = f'from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError("hostile executed")\n'
        for name in ('json.py', 'sitecustomize.py'):
            (hostile / name).write_text(payload)
        for direct in (False, True):
            self.assertEqual(self.call(archive, '--version', cwd=hostile, direct=direct), (0, 'minoetic 0.1.0\n'))
        self.assertFalse(marker.exists())

    def test_archive_check_verify(self):
        archive = self.build()
        workspace = self.root / 'demo'
        self.demo.create_demo(workspace, datetime.now(timezone.utc).replace(microsecond=0))
        self.assertEqual(stat.S_IMODE(workspace.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in workspace.iterdir()))
        args = ('--workspace', str(workspace))
        code, text = self.call(archive, 'check', *args, '--output', 'pass.json')
        self.assertEqual(code, 0, text)
        self.assertEqual(self.call(archive, 'verify', *args, '--result', 'pass.json')[0], 0)
        result = json.loads((workspace / 'pass.json').read_bytes())
        self.assertEqual(result['tool_version'], '0.1.0')
        self.assertEqual(result['brief']['task_counts'], dict(total=3, todo=1, doing=0, done=1, blocked=1))
        self.assertEqual(result['brief']['blocked_tasks'], [dict(id='demo-2', title='Await fictional review')])
        (workspace / 'tasks.json').unlink()
        self.assertEqual(self.call(archive, 'check', *args, '--output', 'missing.json')[0], 1)
        self.assertEqual(self.call(archive, 'check', *args, '--output', 'pass.json')[0], 3)

    def test_demo_refuses_existing_directory(self):
        marker = self.root / 'keep'; marker.write_bytes(b'unchanged')
        with self.assertRaises(FileExistsError):
            self.demo.create_demo(self.root, datetime.now(timezone.utc))
        self.assertEqual(marker.read_bytes(), b'unchanged')
        self.assertEqual([p.name for p in self.root.iterdir()], ['keep'])

    def test_release_packet(self):
        for name in ('CONTRIBUTING.md', 'SECURITY.md', 'SUPPORT.md', 'CHANGELOG.md', 'LICENSE'):
            self.assertTrue((ROOT / name).is_file(), 'Missing release document: ' + name)
        for target in re.findall(r'\]\(([^)]+)\)', (ROOT / 'README.md').read_text()):
            if '://' not in target and not target.startswith('#'):
                self.assertTrue((ROOT / target.split('#')[0]).is_file(), target)
        archive = self.build('minoetic-0.1.0')
        self.assertEqual(self.call(archive, '--version'), (0, 'minoetic 0.1.0\n'))
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(package.read('LICENSE'), (ROOT / 'LICENSE').read_bytes())
        public = [p for p in ROOT.iterdir() if p.suffix == '.md' or p.name == 'LICENSE']
        for directory in ('minoetic', 'tools', 'docs', 'skills'):
            public.extend(p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        for path in public:
            data = path.read_bytes()
            for private in (b'/Users/', b'obsidian-vault', b'SECRET_SENTINEL_7c91', b'Little Snitch Audit'):
                self.assertNotIn(private, data, str(path.relative_to(ROOT)))

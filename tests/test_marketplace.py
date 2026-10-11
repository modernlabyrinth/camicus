import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tools.build_marketplace import build_marketplace

ROOT=Path(__file__).resolve().parents[1]

class MarketplaceTests(unittest.TestCase):
    def test_deterministic_resolvable_and_verified_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary).resolve()
            first, second=base/'first',base/'second'
            build_marketplace(ROOT,first)
            build_marketplace(ROOT,second)
            paths={str(p.relative_to(first)) for p in first.rglob('*') if p.is_file()}
            self.assertEqual(paths,{str(p.relative_to(second)) for p in second.rglob('*') if p.is_file()})
            for path in paths:self.assertEqual((first/path).read_bytes(),(second/path).read_bytes())
            codex=json.loads((first/'.agents/plugins/marketplace.json').read_text())
            claude=json.loads((first/'.claude-plugin/marketplace.json').read_text())
            self.assertEqual(codex['name'],claude['name'])
            self.assertEqual(codex['plugins'][0]['source']['path'],claude['plugins'][0]['source'])
            plugin=first/claude['plugins'][0]['source']
            self.assertTrue((plugin/'bin/camicus').is_file())
            for line in (first/'SHA256SUMS').read_text().splitlines():
                expected,path=line.split('  ',1)
                self.assertEqual(expected,hashlib.sha256((first/path).read_bytes()).hexdigest())
            moved=base/'relocated';first.rename(moved)
            result=subprocess.run([sys.executable,'-I','-S',str(moved/'plugins/camicus/bin/camicus'),'--version'],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn(b'camicus 0.1.0',result.stdout)
    def test_no_overwrite_or_relative_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary).resolve()/'output';output.mkdir()
            with self.assertRaises(FileExistsError):build_marketplace(ROOT,output)
            with self.assertRaises(ValueError):build_marketplace(ROOT,Path('relative'))
    def test_committed_marketplace_checker_rejects_stale_and_extra_files(self):
        import shutil
        from tools.check_marketplace import check
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary).resolve();source=base/'source'
            shutil.copytree(ROOT,source,ignore=shutil.ignore_patterns('.git','__pycache__','dist'))
            built=base/'built';build_marketplace(source,built)
            for child in built.iterdir():
                if child.is_dir():shutil.copytree(child,source/child.name,dirs_exist_ok=True)
                else:shutil.copy2(child,source/child.name)
            check(source)
            binary=source/'plugins/camicus/bin/camicus'
            original=binary.read_bytes();binary.write_bytes(original+b'changed')
            with self.assertRaises(ValueError):check(source)
            binary.write_bytes(original)
            (source/'plugins/camicus/private-sentinel').write_text('must not ship')
            with self.assertRaises(ValueError):check(source)

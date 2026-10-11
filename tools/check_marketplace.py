"""Verify committed public marketplace files equal the current reproducible build."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile

_spec=importlib.util.spec_from_file_location('_camicus_marketplace_builder',Path(__file__).resolve().with_name('build_marketplace.py'))
_module=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def check(root):
    with tempfile.TemporaryDirectory() as temporary:
        built=Path(temporary).resolve()/'marketplace'
        _module.build_marketplace(root,built)
        expected={str(p.relative_to(built)) for p in built.rglob('*') if p.is_file()}
        actual={str(p.relative_to(root)) for directory in ('.agents/plugins','.claude-plugin','plugins/camicus')
                for p in (root/directory).rglob('*') if p.is_file()}
        actual.add('SHA256SUMS')
        if actual!=expected:raise ValueError('generated marketplace inventory differs; regenerate it')
        for name in expected:
            path=root/name
            if path.is_symlink() or not path.is_file() or _module._plugin._regular(root,name)!=(built/name).read_bytes():
                raise ValueError('generated marketplace bytes differ: '+name)
        for line in (root/'SHA256SUMS').read_text().splitlines():
            digest,name=line.split('  ',1)
            if hashlib.sha256(_module._plugin._regular(root,name)).hexdigest()!=digest:
                raise ValueError('marketplace digest mismatch: '+name)
    print('Committed marketplace inventory, bytes and SHA-256 sums match the reproducible build.')

if __name__=='__main__':
    check(Path(__file__).resolve().parents[1])

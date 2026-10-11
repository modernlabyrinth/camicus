"""Build a private, relocatable plugin folder from an explicit reviewed allowlist."""
import argparse
import ctypes
import json
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
_release_spec = importlib.util.spec_from_file_location(
    '_camicus_build_release', Path(__file__).resolve().with_name('build_release.py'))
_release_module = importlib.util.module_from_spec(_release_spec)
_release_spec.loader.exec_module(_release_module)
build_archive, RUNTIME = _release_module.build_archive, _release_module.RUNTIME

SOURCE_FILES = ('plugin.json', '.codex-plugin/plugin.json', '.claude-plugin/plugin.json',
                'skills/weekly-brief/SKILL.md', 'skills/mac-audit/SKILL.md')


def _directory(path):
    """Open every absolute directory component without following links."""
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('parent traversal is not allowed')
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _regular(root, name):
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('source must be a contained relative path')
    directory = None
    descriptor = None
    try:
        directory = _directory(Path(root)/relative.parent)
        descriptor = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 2 * 1024 * 1024:
            raise ValueError('source is not a bounded regular file: '+name)
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, 2 * 1024 * 1024 + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > 2 * 1024 * 1024:
                raise ValueError('source exceeded size bound: '+name)
        after = os.fstat(descriptor)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size,
                                  value.st_mtime_ns, value.st_ctime_ns)
        if identity(before) != identity(after) or total != before.st_size:
            raise ValueError('source changed during read: '+name)
        return b''.join(chunks)
    except OSError as error:
        raise ValueError('missing, linked or unreadable allowlisted source: '+name) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory is not None:
            os.close(directory)


def _publish(stage, destination, parent_fd):
    """Atomically publish without replacing even a racing empty directory."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        function = libc.renameatx_np
        flags = 4  # RENAME_EXCL
    elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        function = libc.renameat2
        flags = 1  # RENAME_NOREPLACE
    else:
        raise OSError('exclusive directory rename is unavailable')
    function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    function.restype = ctypes.c_int
    if function(parent_fd, os.fsencode(stage.name), parent_fd, os.fsencode(destination.name), flags):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def build_plugin(root: Path, destination: Path) -> str:
    root, destination = Path(root), Path(destination)
    if not destination.is_absolute() or '..' in destination.parts:
        raise ValueError('output must be an explicit absolute new directory')
    for parent in (destination.parent, *destination.parent.parents):
        if parent.is_symlink():
            raise ValueError('symlink destination parent is not allowed')
    if os.path.lexists(destination):
        raise FileExistsError(str(destination))
    files = {name: _regular(root/'plugin-source', name) for name in SOURCE_FILES}
    files['LICENSE'] = _regular(root, 'LICENSE')
    files['INSTALL.md'] = _regular(root, 'docs/plugins.md')
    for name in SOURCE_FILES[:3]:
        try:
            manifest = json.loads(files[name])
        except (ValueError, UnicodeError) as error:
            raise ValueError('malformed manifest: '+name) from error
        allowed = {'name', 'version', 'description', 'author', 'license', '$schema'}
        if not isinstance(manifest, dict) or set(manifest)-allowed or manifest.get('name') != 'camicus' or manifest.get('version') != '0.1.0' or not isinstance(manifest.get('description'), str):
            raise ValueError('unexpected manifest: '+name)
    runtime = {name: _regular(root, name) for name in RUNTIME}
    parent_fd = _directory(destination.parent)
    stage = None
    try:
        stage = Path(tempfile.mkdtemp(prefix='.camicus-stage-', dir=destination.parent))
        os.chmod(stage, 0o700)
        (stage/'bin').mkdir(mode=0o700)
        snapshot = stage/'.runtime-source'
        snapshot.mkdir(mode=0o700)
        for name, data in {**runtime, 'LICENSE': files['LICENSE']}.items():
            target = snapshot/name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(data)
        digest = build_archive(snapshot, stage/'bin/camicus')
        shutil.rmtree(snapshot)
        files['bin/camicus.sha256'] = (digest+'  camicus\n').encode()
        for name, data in files.items():
            if name.endswith('SKILL.md'):
                if data.count(b'@ARCHIVE_SHA256@') != 1:
                    raise ValueError('skill must contain exactly one archive digest placeholder')
                data = data.replace(b'@ARCHIVE_SHA256@', digest.encode())
            target = stage/name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with target.open('xb') as output:
                os.fchmod(output.fileno(), 0o600)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        _publish(stage, destination, parent_fd)
        stage = None
        os.fsync(parent_fd)
        return digest
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        os.close(parent_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        digest = build_plugin(Path(__file__).resolve().parents[1], args.output)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error)+'\n')
    print(digest)


if __name__ == '__main__':
    main()

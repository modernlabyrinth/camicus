import errno
import os
import socket
import stat
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from tests.support import ModulesCase, NOW, grant_everyone_acl


class StorageTests(ModulesCase):
    def setUp(self):
        self.storage = self.module('storage')
        self.root = self.workspace()

    def open(self):
        return self.storage.Workspace.open(str(self.root))

    def test_workspace_boundary(self):
        for path in ('relative', str(self.root / '..' / self.root.name)):
            self.problem('unsafe_path', self.storage.Workspace.open, path)
        child = self.root / 'child'; child.mkdir()
        link = self.root / 'alias'; link.symlink_to(child)
        self.problem('unsafe_path', self.storage.Workspace.open, str(link))
        ordinary = self.root / 'file'; ordinary.write_bytes(b'x')
        self.problem('unsafe_path', self.storage.Workspace.open, str(ordinary))
        self.root.chmod(0o770)
        self.problem('unsafe_workspace', self.open)
        self.root.chmod(0o700)
        with patch.object(self.storage.os, 'getuid', return_value=os.getuid() + 1):
            self.problem('unsafe_workspace', self.open)
        with self.open() as work:
            self.assertIsNotNone(work)

    def test_selected_file_types(self):
        regular = self.root / 'real'; regular.write_bytes(b'abc')
        name = self.root / 'project.json'
        with self.open() as work:
            name.symlink_to(regular)
            self.problem('unsafe_path', work.read, name.name, 10); name.unlink()
            os.link(regular, name)
            self.problem('multiple_links', work.read, name.name, 10); name.unlink()
            os.mkfifo(name)
            self.problem('not_regular', work.read, name.name, 10); name.unlink()
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(name))
                self.problem('not_regular', work.read, name.name, 10)
            name.unlink(); name.mkdir()
            self.problem('not_regular', work.read, name.name, 10); name.rmdir()
            with patch.object(self.storage.os, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), patch.object(self.storage.os, 'open') as opened:
                self.problem('not_regular', work.read, name.name, 10)
                opened.assert_not_called()

    def test_descriptor_rechecked_nonblocking(self):
        path = self.root / 'project.json'; path.write_bytes(b'abc')
        real_open, real_fstat = os.open, os.fstat
        with self.open() as work:
            with patch.object(self.storage.os, 'open', wraps=real_open) as opened, patch.object(self.storage.os, 'fstat', return_value=SimpleNamespace(st_mode=stat.S_IFIFO)), patch.object(self.storage.os, 'read') as read:
                self.problem('not_regular', work.read, path.name, 10)
                self.assertTrue(opened.call_args.args[1] & os.O_NONBLOCK)
                read.assert_not_called()

    def test_bounded_read(self):
        path = self.root / 'project.json'; path.write_bytes(b'abc')
        with self.open() as work, patch('minoetic.models.utc_now', return_value=NOW):
            self.problem('too_large', work.read, path.name, 2)
            snapshot = work.read(path.name, 3)
            self.assertEqual((snapshot.data, snapshot.read_at), (b'abc', NOW))
            real_read = os.read
            def grow(fd, count):
                with path.open('ab') as stream:
                    stream.write(b'12345')
                return real_read(fd, count)
            with patch.object(self.storage.os, 'read', side_effect=grow):
                self.problem('too_large', work.read, path.name, 4)

    def test_result_alias(self):
        with self.open() as work:
            for name in ('project.json', 'tasks.json', '../new.json', '/new.json', 'a/b.json', 'new.txt', 'evil\n.json', ''):
                self.problem('unsafe_path', work.preflight_output, name)
            source = self.root / 'project.json'; source.write_bytes(b'abc')
            alias = self.root / 'result.json'; os.link(source, alias)
            self.problem('output_conflict', work.preflight_output, alias.name)
            self.problem('multiple_links', work.read, alias.name, 10)

    def test_read_denied(self):
        with self.open() as work:
            self.problem('missing_file', work.read, 'project.json', 10)
            with patch.object(self.storage.os, 'stat', side_effect=PermissionError()):
                problem = self.problem('read_denied', work.read, 'project.json', 10)
                self.assertEqual(problem.state, 'not_checked')

    def test_replaced_source_same_bytes(self):
        path = self.root / 'project.json'; path.write_bytes(b'abc')
        with self.open() as work:
            snapshot = work.read(path.name, 10)
            replacement = self.root / 'replacement'; replacement.write_bytes(b'abc')
            replacement.replace(path)
            self.problem('source_changed', work.unchanged, path.name, snapshot, 10)

    def test_same_length_edit_restored_mtime(self):
        path = self.root / 'project.json'; path.write_bytes(b'abc')
        with self.open() as work:
            snapshot = work.read(path.name, 10)
            path.write_bytes(b'xyz')
            os.utime(path, ns=(snapshot.stat.st_atime_ns, snapshot.stat.st_mtime_ns))
            self.problem('source_changed', work.unchanged, path.name, snapshot, 10)

    def test_final_read_denied(self):
        path = self.root / 'project.json'; path.write_bytes(b'abc')
        with self.open() as work:
            snapshot = work.read(path.name, 10)
            with patch.object(self.storage.os, 'stat', side_effect=PermissionError()):
                problem = self.problem('source_unobserved', work.unchanged, path.name, snapshot, 10)
                self.assertEqual(problem.state, 'not_checked')

    def test_publish_complete_private_and_exclusive(self):
        with self.open() as work:
            work.preflight_output('out.json')
            work.publish('out.json', b'complete')
            self.assertEqual((self.root / 'out.json').read_bytes(), b'complete')
            self.assertEqual(stat.S_IMODE((self.root / 'out.json').stat().st_mode), 0o600)
            self.assertEqual([p.name for p in self.root.iterdir()], ['out.json'])
            self.problem('output_conflict', work.publish, 'out.json', b'changed')
            self.assertEqual((self.root / 'out.json').read_bytes(), b'complete')

    def test_publication_faults_and_no_clobber_retry(self):
        for fault in ('write', 'file_fsync', 'link', 'unlink', 'directory_fsync'):
            with self.subTest(fault=fault):
                root = self.workspace()
                with self.storage.Workspace.open(str(root)) as work:
                    real_fsync = os.fsync
                    def fsync(fd):
                        isdir = stat.S_ISDIR(os.fstat(fd).st_mode)
                        if (fault == 'directory_fsync' and isdir) or (fault == 'file_fsync' and not isdir):
                            raise OSError(errno.EIO, 'injected')
                        return real_fsync(fd)
                    function = 'fsync' if 'fsync' in fault else fault
                    effect = fsync if function == 'fsync' else OSError(errno.EIO, 'injected')
                    with patch.object(self.storage.os, function, side_effect=effect):
                        self.problem('publication_failed', work.publish, 'out.json', b'whole result')
                    final = root / 'out.json'
                    if fault in ('unlink', 'directory_fsync'):
                        self.assertEqual(final.read_bytes(), b'whole result')
                        self.problem('output_conflict', work.publish, final.name, b'new')
                        self.assertEqual(final.read_bytes(), b'whole result')
                    else:
                        self.assertFalse(final.exists())
                    for temp in root.iterdir():
                        self.assertEqual(stat.S_IMODE(temp.stat().st_mode), 0o600)
                        if temp.name != 'out.json':
                            self.assertFalse(temp.name.endswith('.json'))

    def test_cleanup_preserves_substituted_inode(self):
        real_link = os.link
        replacement = []
        def replace_temp(src, dst, **kwargs):
            temp = self.root / src
            temp.unlink(); temp.write_bytes(b'unrelated')
            replacement.append(temp)
            raise OSError(errno.EIO, 'injected')
        with self.open() as work, patch.object(self.storage.os, 'link', side_effect=replace_temp):
            self.problem('publication_failed', work.publish, 'out.json', b'candidate')
        self.assertEqual(replacement[0].read_bytes(), b'unrelated')

    def test_concurrent_publishers(self):
        barrier = Barrier(2)
        def publish(candidate):
            with self.open() as work:
                work.preflight_output('out.json')
                barrier.wait(timeout=5)
                try:
                    work.publish('out.json', candidate)
                    return 'ok'
                except self.module('models').Problem as problem:
                    return problem.reason
        candidates = (b'a' * 65536, b'b' * 65536)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(publish, candidates))
        self.assertEqual(sorted(outcomes), ['ok', 'output_conflict'])
        self.assertIn((self.root / 'out.json').read_bytes(), candidates)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_workspace_acl_read_inheritance_and_effective_write_rejected(self):
        for mode, permissions in ((0o700, 2), (0o755, 2), (0o755, 4 | 8 | 64)):
            with self.subTest(mode=mode, permissions=permissions):
                root = self.workspace(); root.chmod(mode)
                fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    grant_everyone_acl(fd, permissions, inherit=True)
                finally:
                    os.close(fd)
                self.problem('unsafe_workspace', self.storage.Workspace.open, str(root))
                self.assertEqual(stat.S_IMODE(root.stat().st_mode), mode)

    def test_temp_acl_checked_before_private_bytes_written(self):
        real_open = os.open
        def create_with_acl(name, flags, *args, **kwargs):
            fd = real_open(name, flags, *args, **kwargs)
            if flags & os.O_CREAT:
                grant_everyone_acl(fd)
            return fd
        with self.open() as work, patch.object(self.storage.os, 'open', side_effect=create_with_acl), patch.object(self.storage.os, 'write', side_effect=AssertionError('Private bytes reached an ACL-bearing temporary file')) as write:
            self.problem('publication_failed', work.publish, 'out.json', b'private')
            write.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_acl_inspection_unavailable_never_safe(self):
        self.assertTrue(hasattr(self.storage, '_has_extended_acl'), 'ACL inspection not implemented')
        with patch.object(self.storage, '_has_extended_acl', side_effect=PermissionError(errno.EACCES, 'private')):
            problem = self.problem('read_denied', self.open)
            self.assertEqual(problem.state, 'not_checked')
        with self.open() as work, patch.object(self.storage, '_has_extended_acl', side_effect=OSError(errno.EIO, 'private')):
            self.problem('publication_failed', work.publish, 'out.json', b'private')
        self.assertFalse((self.root / 'out.json').exists())

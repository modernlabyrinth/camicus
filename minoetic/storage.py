"""Descriptor-relative reads and exclusive publication in an explicit workspace."""
from dataclasses import dataclass
from datetime import datetime
import ctypes
import errno
import os
import stat
import sys
from uuid import uuid4
from . import models
from .models import Problem


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    stat: os.stat_result
    read_at: datetime


def valid_name(name: str, *, result: bool = False) -> bool:
    return (isinstance(name, str) and name.endswith('.json') and len(name) > 5
            and '/' not in name and '\\' not in name
            and not any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in name)
            and (not result or name.casefold() not in ('project.json', 'tasks.json')))


def _load_acl_api():
    if sys.platform != 'darwin':
        return None
    try:
        library = ctypes.CDLL(None, use_errno=True)
        get_acl, free_acl = library.acl_get_fd_np, library.acl_free
        get_acl.argtypes = (ctypes.c_int, ctypes.c_int)
        get_acl.restype = ctypes.c_void_p
        free_acl.argtypes = (ctypes.c_void_p,)
        free_acl.restype = ctypes.c_int
        return get_acl, free_acl
    except (AttributeError, OSError):
        return None


_ACL_API = _load_acl_api()


def acl_available() -> bool:
    return _ACL_API is not None


def _has_extended_acl(fd: int) -> bool:
    if _ACL_API is None:
        raise OSError(errno.ENOTSUP, 'ACL inspection unavailable')
    get_acl, free_acl = _ACL_API
    ctypes.set_errno(0)
    acl = get_acl(fd, 0x100)  # Darwin ACL_TYPE_EXTENDED, from sys/acl.h.
    if not acl:
        error = ctypes.get_errno()
        if error == errno.ENOENT:
            return False  # Open descriptor exists; no extended ACL is attached.
        raise OSError(error or errno.EIO, 'ACL inspection failed')
    # Reject any returned ACL, including an empty ACL object. Do not guess which
    # mixed allow/deny/inheritance entries are harmless or modify user permissions.
    if free_acl(acl) != 0:
        raise OSError(ctypes.get_errno() or errno.EIO, 'ACL release failed')
    return True


def _private_directory(fd):
    metadata = os.fstat(fd)
    if (metadata.st_uid != os.getuid() or metadata.st_mode & 0o022
            or _has_extended_acl(fd)):
        raise Problem('unsafe_workspace')


def _identity(value):
    return tuple(getattr(value, key) for key in (
        'st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def _regular(value):
    if stat.S_ISLNK(value.st_mode):
        raise Problem('unsafe_path')
    if not stat.S_ISREG(value.st_mode):
        raise Problem('not_regular')
    if value.st_nlink != 1:
        raise Problem('multiple_links')


def _read_error(exc):
    if exc.errno in (errno.EACCES, errno.EPERM) or isinstance(exc, PermissionError):
        return Problem('read_denied', 'not_checked')
    if exc.errno == errno.ENOENT:
        return Problem('missing_file')
    if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.ENAMETOOLONG):
        return Problem('unsafe_path')
    return Problem('source_unobserved', 'not_checked')


class Workspace:
    def __init__(self, descriptors):
        self._descriptors = descriptors
        self._fd = descriptors[-1]

    @classmethod
    def open(cls, path: str):
        if (not isinstance(path, str) or not path.startswith('/') or '\x00' in path
                or '..' in path.split('/') or any(0xD800 <= ord(c) <= 0xDFFF for c in path)):
            raise Problem('unsafe_path')
        descriptors = []
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            descriptors.append(os.open('/', flags))
            for component in path.split('/'):
                if component not in ('', '.'):
                    descriptors.append(os.open(component, flags, dir_fd=descriptors[-1]))
            _private_directory(descriptors[-1])
            return cls(descriptors)
        except BaseException as exc:
            for fd in reversed(descriptors):
                os.close(fd)
            if isinstance(exc, OSError):
                raise _read_error(exc) from None
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        for fd in reversed(self._descriptors):
            os.close(fd)
        self._descriptors.clear()

    def read(self, name: str, limit: int) -> Snapshot:
        if not valid_name(name):
            raise Problem('unsafe_path')
        try:
            before = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
            _regular(before)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self._fd)
            try:
                opened = os.fstat(fd)
                _regular(opened)
                if _identity(before) != _identity(opened):
                    raise Problem('source_changed')
                if opened.st_size > limit:
                    raise Problem('too_large')
                data = bytearray()
                while len(data) <= limit:
                    part = os.read(fd, min(65536, limit + 1 - len(data)))
                    if not part:
                        break
                    data.extend(part)
                after = os.fstat(fd)
                if len(data) > limit or after.st_size > limit:
                    raise Problem('too_large')
                if _identity(opened) != _identity(after):
                    raise Problem('source_changed')
                return Snapshot(bytes(data), after, models.utc_now())
            finally:
                os.close(fd)
        except OSError as exc:
            raise _read_error(exc) from None

    def preflight_output(self, name: str) -> None:
        if not valid_name(name, result=True):
            raise Problem('unsafe_path')
        try:
            os.stat(name, dir_fd=self._fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError:
            raise Problem('publication_failed') from None
        raise Problem('output_conflict')

    def unchanged(self, name: str, snapshot: Snapshot, limit: int) -> None:
        try:
            current = self.read(name, limit)
        except Problem as exc:
            if exc.state == 'not_checked':
                raise Problem('source_unobserved', 'not_checked') from None
            raise Problem('source_changed') from None
        if _identity(snapshot.stat) != _identity(current.stat) or snapshot.data != current.data:
            raise Problem('source_changed')

    def _remove_owned(self, name, owned):
        current = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino):
            raise OSError(errno.EIO, 'temporary identity changed')
        os.unlink(name, dir_fd=self._fd)

    def publish(self, name: str, data: bytes) -> None:
        self.preflight_output(name)
        temporary = '.minoetic-' + uuid4().hex + '.tmp'
        fd = owned = None
        cleanup_attempted = False
        try:
            _private_directory(self._fd)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self._fd)
            owned = os.fstat(fd)
            os.fchmod(fd, 0o600)
            if _has_extended_acl(fd):
                raise OSError(errno.EACCES, 'temporary ACL is not private')
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError(errno.EIO, 'short write')
                view = view[written:]
            os.fsync(fd)
            os.link(temporary, name, src_dir_fd=self._fd, dst_dir_fd=self._fd,
                    follow_symlinks=False)
            cleanup_attempted = True
            self._remove_owned(temporary, owned)
            os.fsync(self._fd)
        except OSError as exc:
            raise Problem('output_conflict' if exc.errno == errno.EEXIST else 'publication_failed') from None
        except Problem:
            raise Problem('publication_failed') from None
        finally:
            if owned is not None and not cleanup_attempted:
                try:
                    self._remove_owned(temporary, owned)
                except OSError:
                    pass  # Preserve an unobserved or substituted entry, never unlink it blindly.
            if fd is not None:
                os.close(fd)

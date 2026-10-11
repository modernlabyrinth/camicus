from datetime import datetime, timezone
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
STAMP = "2026-10-11T12:00:00Z"
INPUT = "minoetic.weekly-input/1"
IDS = ("workspace_boundary", "project_read", "project_schema", "project_freshness",
       "tasks_read", "tasks_schema", "tasks_freshness", "project_identity",
       "brief_invariants", "source_stability")
LIMITATIONS = ["Source claims are not verified as true.",
              "Upstream connections and agent prose are not checked.",
              "Checks apply only at observed checkpoints.",
              "This is unsigned local evidence, not a security assessment."]


def grant_everyone_acl(fd, permissions=2, inherit=False):
    """Give a fictional fixture a real macOS ACL without a shell subprocess."""
    lib = ctypes.CDLL(None, use_errno=True)
    pointer, integer = ctypes.c_void_p, ctypes.c_int
    signatures = {
        'acl_init': ([integer], pointer),
        'acl_create_entry': ([ctypes.POINTER(pointer), ctypes.POINTER(pointer)], integer),
        'acl_set_tag_type': ([pointer, integer], integer),
        'mbr_gid_to_uuid': ([ctypes.c_uint, pointer], integer),
        'acl_set_qualifier': ([pointer, pointer], integer),
        'acl_get_permset': ([pointer, ctypes.POINTER(pointer)], integer),
        'acl_add_perm': ([pointer, integer], integer),
        'acl_get_flagset_np': ([pointer, ctypes.POINTER(pointer)], integer),
        'acl_add_flag_np': ([pointer, integer], integer),
        'acl_set_fd_np': ([integer, pointer, integer], integer),
        'acl_free': ([pointer], integer),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(lib, name); function.argtypes = arguments; function.restype = result
    def call(name, *args):
        if getattr(lib, name)(*args) != 0:
            raise OSError(ctypes.get_errno(), 'fixture ACL operation failed')
    acl = pointer(lib.acl_init(1))
    if not acl:
        raise OSError(ctypes.get_errno(), 'fixture ACL allocation failed')
    try:
        entry, perms, flags = pointer(), pointer(), pointer()
        call('acl_create_entry', ctypes.byref(acl), ctypes.byref(entry))
        call('acl_set_tag_type', entry, 1)  # ACL_EXTENDED_ALLOW
        import grp
        group_uuid = (ctypes.c_ubyte * 16)()
        call('mbr_gid_to_uuid', grp.getgrnam('everyone').gr_gid, group_uuid)
        call('acl_set_qualifier', entry, group_uuid)
        call('acl_get_permset', entry, ctypes.byref(perms))
        for bit in range(1, 14):
            if permissions & (1 << bit):
                call('acl_add_perm', perms, 1 << bit)
        if inherit:
            call('acl_get_flagset_np', entry, ctypes.byref(flags))
            for flag in (1 << 5, 1 << 6):  # file and directory inheritance
                call('acl_add_flag_np', flags, flag)
        call('acl_set_fd_np', fd, acl, 0x100)
    finally:
        call('acl_free', acl)


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def project_bytes(**overrides):
    value = dict(schema_version=INPUT, project_id="demo", as_of=STAMP,
                 summary="Fictional project")
    return dump(value | overrides)


def tasks_bytes(records=None, **overrides):
    if records is None:
        records = [dict(id=i, title=i, state=s) for i, s in
                   (("a", "todo"), ("b", "blocked"), ("c", "done"))]
    return dump(dict(schema_version=INPUT, project_id="demo", as_of=STAMP,
                     tasks=records) | overrides)


def valid_result():
    return dict(schema_version="minoetic.weekly-result/1", tool_version="0.1.0",
                contract_version="weekly-brief/1",
                run_id="3c8362da-1ddb-4b5f-a17a-bc8bd538e341",
                started_at=STAMP, finished_at=STAMP, scope="local-weekly-brief",
                sources={alias: dict(sha256=hashlib.sha256(data).hexdigest(),
                                     byte_length=len(data), as_of=STAMP, read_at=STAMP)
                         for alias, data in (("project", project_bytes()), ("tasks", tasks_bytes()))},
                checks=[dict(id=i, state="passed", reason="ok", source=None, field=None)
                        for i in IDS], overall="passed",
                brief=dict(project_id="demo", project_summary="Fictional project",
                           source_as_of=dict(project=STAMP, tasks=STAMP),
                           task_counts=dict(total=3, todo=1, doing=0, done=1, blocked=1),
                           blocked_tasks=[dict(id="b", title="b")]),
                limitations=LIMITATIONS.copy())


class ModulesCase(unittest.TestCase):
    def module(self, name):
        try:
            return importlib.import_module("minoetic." + name)
        except ModuleNotFoundError as exc:
            if exc.name in ("minoetic", "minoetic." + name):
                self.fail("Required module is not implemented: " + name)
            raise

    def problem(self, code, call, *args, **kwargs):
        model = self.module("models")
        with self.assertRaises(model.Problem) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.reason, code)
        return caught.exception

    def workspace(self):
        temp = tempfile.TemporaryDirectory(prefix="minoetic-test-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        root.chmod(0o700)
        return root

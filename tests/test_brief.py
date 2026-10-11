import copy
from tests.support import ModulesCase, project_bytes, tasks_bytes, valid_result


class BriefTests(ModulesCase):
    def setUp(self):
        self.c = self.module("contracts"); self.b = self.module("brief")
        self.project = self.c.parse_project(project_bytes())
        self.tasks = self.c.parse_tasks(tasks_bytes())

    def test_exact_brief(self):
        self.assertEqual(self.b.build_brief(self.project, self.tasks), valid_result()["brief"])
        self.assertEqual(self.b.verify_brief(valid_result()["brief"], self.project, self.tasks).state, "passed")

    def test_empty_tasks(self):
        got = self.b.build_brief(self.project, self.c.parse_tasks(tasks_bytes([])))
        self.assertEqual(got["task_counts"], dict(total=0, todo=0, doing=0, done=0, blocked=0))
        self.assertEqual(got["blocked_tasks"], [])

    def test_blocker_omission(self):
        r = valid_result()["brief"]; r["blocked_tasks"] = []
        self.assertEqual(self.b.verify_brief(r, self.project, self.tasks).reason, "brief_mismatch")

    def test_copied_context_changed(self):
        for key, value in (("project_summary", "Invented"), ("project_id", "other"),
                           ("source_as_of", {}), ("task_counts", {})):
            r = copy.deepcopy(valid_result()["brief"]); r[key] = value
            self.assertEqual(self.b.verify_brief(r, self.project, self.tasks).state, "failed")

    def test_sorted_blockers(self):
        tasks = self.c.parse_tasks(tasks_bytes([dict(id=i, title=i, state="blocked") for i in ("z", "a")]))
        r = self.b.build_brief(self.project, tasks)
        self.assertEqual([x["id"] for x in r["blocked_tasks"]], ["a", "z"])
        r["blocked_tasks"].reverse()
        self.assertEqual(self.b.verify_brief(r, self.project, tasks).state, "failed")

    def test_maximum_unicode_brief(self):
        p = project_bytes(summary="🧵" * 2000)
        t = tasks_bytes([dict(id=f"t{i}", title="🧵" * 240, state="blocked") for i in range(1000)])
        self.assertLessEqual(len(t), 1048576)
        project, tasks = self.c.parse_project(p), self.c.parse_tasks(t)
        brief = self.b.build_brief(project, tasks)
        self.assertEqual(len(brief["blocked_tasks"]), 1000)
        self.assertEqual(self.b.verify_brief(brief, project, tasks).state, "passed")
        r = valid_result(); r["brief"] = brief
        data = self.c.encode_result(r)
        self.assertLessEqual(len(data), 2097152)
        self.assertIn("🧵".encode(), data)

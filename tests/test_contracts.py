import copy
from datetime import timedelta
import json
from tests.support import ModulesCase, NOW, STAMP, dump, project_bytes, tasks_bytes, valid_result


class ContractTests(ModulesCase):
    def setUp(self):
        self.c = self.module("contracts")

    def test_valid_structural_inputs(self):
        self.assertEqual(self.c.parse_project(project_bytes()).summary, "Fictional project")
        self.assertEqual(len(self.c.parse_tasks(tasks_bytes()).tasks), 3)

    def test_duplicate_json_key(self):
        self.problem("duplicate_key", self.c.parse_project, b'{"a":1,"a":2}')

    def test_unknown_and_missing_fields(self):
        self.problem("schema_mismatch", self.c.parse_project, project_bytes(extra=1))
        for field in ("schema_version", "project_id", "as_of", "summary"):
            value = json.loads(project_bytes()); del value[field]
            self.problem("schema_mismatch", self.c.parse_project, dump(value))
        for value in ([], None, True, 1, "text"):
            self.problem("schema_mismatch", self.c.parse_project, dump(value))
        self.problem("schema_mismatch", self.c.parse_project, project_bytes(schema_version=1))

    def test_invalid_encoding_and_surrogates(self):
        self.problem("invalid_utf8", self.c.parse_project, b'\xff')
        data = project_bytes().replace(b'Fictional project', b'\\ud800')
        self.problem("invalid_text", self.c.parse_project, data)

    def test_controls_and_blank_text(self):
        for text in (" ", "\x00", "\n", "\x7f", "\x85"):
            self.problem("invalid_text", self.c.parse_project, project_bytes(summary=text))

    def test_all_length_limits(self):
        self.c.parse_project(project_bytes(summary="a" * 2000, project_id="a" * 64))
        self.problem("invalid_text", self.c.parse_project, project_bytes(summary="a" * 2001))
        for ident in ("", "a" * 65, "a/b", "a b", "_id", "é"):
            self.problem("invalid_id", self.c.parse_project, project_bytes(project_id=ident))
        record = dict(id="a", title="x" * 240, state="doing")
        self.c.parse_tasks(tasks_bytes([record]))
        self.problem("invalid_text", self.c.parse_tasks, tasks_bytes([record | {"title": "x" * 241}]))
        self.problem("schema_mismatch", self.c.parse_tasks, tasks_bytes([record] * 1001))

    def test_depth_limit(self):
        self.problem("schema_mismatch", self.c.parse_project, b'[' * 8 + b'0' + b']' * 8)
        self.problem("excessive_depth", self.c.parse_project, b'[' * 9 + b'0' + b']' * 9)
        self.c.parse_project(project_bytes(summary='[{"' * 30))

    def test_duplicate_task_ids(self):
        row = dict(id="a", title="A", state="done")
        self.problem("duplicate_task_id", self.c.parse_tasks, tasks_bytes([row, row]))

    def test_invalid_states(self):
        for state in ("complete", "", 1, True, None):
            self.problem("schema_mismatch", self.c.parse_tasks,
                         tasks_bytes([dict(id="a", title="A", state=state)]))

    def test_nonfinite_and_huge_numbers(self):
        for value in (b'NaN', b'Infinity', b'-Infinity', b'1e999'):
            self.problem("nonfinite_number", self.c.parse_project, b'{"summary":' + value + b'}')
        self.problem("invalid_json", self.c.parse_project, b'1' * 5000)

    def test_timestamp_is_exact_utc(self):
        for value in ("2026-10-11", STAMP.replace("Z", "+00:00"), "2026-02-30T00:00:00Z", True):
            self.problem("schema_mismatch", self.c.parse_project, project_bytes(as_of=value))

    def test_freshness_boundaries(self):
        for delta, state, code in ((-timedelta(days=7), "passed", "ok"),
                                  (timedelta(minutes=5), "passed", "ok"),
                                  (-timedelta(days=7, seconds=1), "failed", "stale_as_of"),
                                  (timedelta(minutes=5, seconds=1), "failed", "future_as_of")):
            got = self.c.freshness(NOW + delta, NOW, "project")
            self.assertEqual((got.state, got.reason), (state, code))

    def test_source_byte_limit(self):
        data = project_bytes(); padded = data + b' ' * (1048576 - len(data))
        self.c.parse_project(padded)
        self.problem("too_large", self.c.parse_project, padded + b' ')

    def test_result_byte_limit(self):
        data = dump(valid_result()); padded = data + b' ' * (2097152 - len(data))
        self.c.validate_result(padded, "0.1.0")
        self.problem("too_large", self.c.validate_result, padded + b' ', "0.1.0")
        self.problem("too_large", self.c.encode_result, {"text": "x" * 2097152})

    def test_boolean_is_not_integer(self):
        r = valid_result(); r["brief"]["task_counts"]["todo"] = True
        self.problem("invalid_result", self.c.validate_result, dump(r), "0.1.0")
        r = valid_result(); r["sources"]["project"]["byte_length"] = True
        self.problem("invalid_result", self.c.validate_result, dump(r), "0.1.0")

    def test_receipt_integrity(self):
        mutations = [lambda r: r.update(extra=True),
                     lambda r: r.update(overall="unknown"),
                     lambda r: r.update(finished_at="2026-10-10T12:00:00Z"),
                     lambda r: r.update(run_id="not-a-uuid"),
                     lambda r: r["checks"][0].update(id="invented"),
                     lambda r: r["checks"][0].update(state="failed"),
                     lambda r: r["checks"].append(copy.deepcopy(r["checks"][0])),
                     lambda r: r["sources"].update(other=None),
                     lambda r: r["sources"].update(project=None),
                     lambda r: r["sources"]["project"].update(read_at="2026-10-12T00:00:00Z"),
                     lambda r: r["sources"]["project"].update(sha256="g" * 64),
                     lambda r: r["checks"][0].update(field="SECRET_SENTINEL"),
                     lambda r: r["brief"].update(extra=True),
                     lambda r: r.update(brief=None),
                     lambda r: r.update(limitations=[])]
        self.c.validate_result(dump(valid_result()), "0.1.0")
        for mutate in mutations:
            r = valid_result(); mutate(r)
            with self.subTest(mutation=mutations.index(mutate)):
                self.problem("invalid_result", self.c.validate_result, dump(r), "0.1.0")
        for key in ("tool_version", "contract_version", "schema_version"):
            r = valid_result(); r[key] = "future"
            self.problem("unsupported_result_version", self.c.validate_result, dump(r), "0.1.0")

    def test_failure_receipt_shape(self):
        r = valid_result(); r.update(overall="failed", brief=None)
        r["sources"]["project"] = None
        for c in r["checks"]:
            if c["id"] == "project_read": c.update(state="failed", reason="missing_file")
            elif c["id"] in ("project_schema", "project_freshness", "project_identity", "brief_invariants", "source_stability"):
                c.update(state="not_checked", reason="dependency_unavailable")
        self.c.validate_result(dump(r), "0.1.0")

    def test_aggregate_precedence(self):
        m = self.module("models")
        self.assertEqual(self.c.aggregate((m.Check("a", "not_checked", "read_denied"),
                                          m.Check("b", "failed", "missing_file"))), "failed")
        self.assertEqual(self.c.aggregate((m.Check("a", "not_checked", "read_denied"),)), "not_checked")

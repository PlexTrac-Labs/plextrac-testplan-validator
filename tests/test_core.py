"""The UI-independent core: running the checks, plan statistics, check groups, unreadable files."""
import ast
import unittest

import yaml

from tests.helpers import OWASP_DIR, SCRIPT, load_script, run_cli, variant_text

vtp = load_script()


class CoreTest(unittest.TestCase):
    def test_run_checks(self):
        res = vtp.run_checks(variant_text("broken"))
        self.assertEqual(sorted(e["check"] for e in res.report.errors), ["reference.dangling", "tags.nonempty"])
        self.assertEqual([w["check"] for w in res.report.warnings], ["reference.unused"])
        self.assertIsNone(res.parse_error)
        bad = vtp.run_checks(variant_text("syntax"))
        self.assertIsNone(bad.doc)
        self.assertIsNotNone(bad.parse_error)
        self.assertEqual(bad.report.errors[-1]["check"], "yaml.parse")

    def test_issue_key(self):
        item = {"check": "id.format", "message": "bad id", "where": "tactics[0] X"}
        self.assertEqual(vtp.issue_key(item), ("id.format", "bad id", "tactics[0] X"))

    def test_plan_stats(self):
        st = vtp.plan_stats(yaml.safe_load(variant_text("ok")))
        self.assertEqual(st.counts, {"methodologies": 1, "tactics": 2, "techniques": 2, "repositories": 1, "procedures": 4})
        self.assertEqual((st.objects, st.links), (10, 16))

    def test_plan_stats_owasp(self):
        path = OWASP_DIR / "OWASP_WSTG.yaml"
        if not path.exists():
            self.skipTest("OWASP_WSTG.yaml not present")
        st = vtp.plan_stats(yaml.safe_load(path.read_text(encoding="utf-8")))
        self.assertEqual((st.objects, st.links), (115, 295))

    def test_group_of(self):
        for check, label in {"yaml.bom": "YAML syntax", "schema.field": "Structure", "id.format": "IDs",
                             "runbook.alias": "References", "reference.unused": "References",
                             "tags.nonempty": "Content", "content.empty": "Content", "other.x": "Content"}.items():
            self.assertEqual(vtp.group_of(check), label)

    def test_unreadable_non_utf8_exits_2(self):
        run = run_cli(["latin1.yaml"], {"latin1.yaml": "shortName: caf\xe9\n".encode("latin-1")})
        self.assertEqual((run.code, run.stdout), (2, ""))
        self.assertTrue(run.stderr.startswith("cannot read latin1.yaml: 'utf-8' codec can't decode"))

    def test_source_parses_as_python_38(self):
        ast.parse(SCRIPT.read_text(encoding="utf-8"), feature_version=(3, 8))


if __name__ == "__main__":
    unittest.main()

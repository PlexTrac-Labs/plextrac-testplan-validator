"""Repair preview: which problems a repair fixes, what it changes, and what it leaves alone."""
import copy
import timeit
import unittest

import yaml

from tests.helpers import OWASP_DIR, load_script, variant_text

vtp = load_script()

AUTO = {"dangling_methodology": True, "tags_nonempty": True, "extra_anchor": True, "bom": True,
        "runbook_copy": True, "runbook_missing": True, "tab_in_value": True,
        "tags_null": False, "tags_missing": False, "dangling_repository": False}


class RepairPreviewTest(unittest.TestCase):
    def test_auto_labels_match_a_real_repair(self):
        for name, fixable in AUTO.items():
            with self.subTest(variant=name):
                text = variant_text(name)
                res = vtp.run_checks(text)
                before = {vtp.issue_key(i) for i in res.report.errors + res.report.warnings}
                after = vtp.run_checks(vtp.repaired_text(res.doc, text)[0]).report
                gone = before - {vtp.issue_key(i) for i in after.errors + after.warnings}
                self.assertEqual(vtp.auto_fixed(res.doc, res.report), gone)
                self.assertEqual(bool(gone), fixable)

    def test_original_document_untouched(self):
        text = variant_text("broken")
        res = vtp.run_checks(text)
        snapshot = copy.deepcopy(res.doc)
        vtp.auto_fixed(res.doc, res.report)
        vtp.repaired_text(res.doc, text)
        self.assertEqual(res.doc, snapshot)

    def test_repair_changes(self):
        text = variant_text("broken")
        res = vtp.run_checks(text)
        _, after = vtp.repaired_text(res.doc, text)
        self.assertEqual(vtp.repair_changes(res.doc, after), [
            vtp.Change("tactics", "MINI-T1", "methodologyIds", ["c" + "8" * 24]),
            vtp.Change("procedures", "MINI-P2", "tags", ["web"])])

    def test_file_fixes(self):
        for name, lines in {"broken": [], "extra_anchor": ["stray anchors removed"],
                            "bom": ["byte order mark dropped"], "tab_in_value": ["tab characters escaped"],
                            "runbook_copy": ["runbook made an alias of testPlan"],
                            "runbook_missing": ["runbook section added"]}.items():
            self.assertEqual(vtp.file_fixes(vtp.run_checks(variant_text(name)).report), lines, name)

    def test_can_repair(self):
        self.assertTrue(vtp.can_repair(yaml.safe_load(variant_text("ok"))))
        for doc in ({"methodologies": []}, {"testPlan": None}, [1, 2], None):
            self.assertFalse(vtp.can_repair(doc))

    def test_auto_fixed_is_fast(self):
        path = OWASP_DIR / "OWASP_MASTG.yaml"
        if not path.exists():
            self.skipTest("OWASP_MASTG.yaml not present")
        res = vtp.run_checks(path.read_text(encoding="utf-8"))
        best = min(timeit.timeit(lambda: vtp.auto_fixed(res.doc, res.report), number=1) for _ in range(3))
        self.assertLess(best, 0.1)


if __name__ == "__main__":
    unittest.main()

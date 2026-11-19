"""The interactive repair: offer, save-as name checks, receipt and re-check."""
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import GOLDEN, load_script, variant_text

vtp = load_script()
CAPS = vtp.Caps(True, True, True, 100, 40)


def REPLACE(s):
    return ["home"] + ["delete"] * 60 + list(s)


class RepairFlowTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "broken.yaml"
        self.text = variant_text("broken")
        self.path.write_text(self.text, encoding="utf-8")
        self.res = vtp.run_checks(self.text)
        self.auto = vtp.auto_fixed(self.res.doc, self.res.report)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def flow(self, keys):
        out = io.StringIO()
        result = vtp.offer_repair(self.path, self.text, self.res, self.auto, out, iter(keys), CAPS)
        return result, vtp.strip_ansi(out.getvalue())

    def test_accept_defaults(self):
        written, s = self.flow(["enter", "enter"])
        self.assertEqual(written, self.dir / "broken.fixed.yaml")
        self.assertEqual(written.read_text(encoding="utf-8"), (GOLDEN / "broken_fix.out.yaml").read_text(encoding="utf-8"))
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.text)
        for line in ("🔧 2 of 3 problems can be repaired automatically  ·  original file untouched",
                     "🔧 Repaired copy · broken.fixed.yaml", "tactics › MINI-T1", "− " + "c" + "8" * 24,
                     "− web  → []", "✔ 2 repairs     ✎ 1 left for you     original file untouched",
                     "re-checked · broken.fixed.yaml", " READY TO IMPORT ", "1 warning left"):
            self.assertIn(line, s)

    def test_decline(self):
        written, s = self.flow(["n"])
        self.assertIsNone(written)
        self.assertIn("Cancelled. Nothing was written.", s)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["broken.yaml"])

    def test_refuses_bad_names(self):
        (self.dir / "sub").mkdir()
        keys = (["enter"] + REPLACE("") + ["enter"] + REPLACE("broken.yaml") + ["enter"]
                + REPLACE("sub") + ["enter", "esc"])
        written, s = self.flow(keys)
        self.assertIsNone(written)
        for msg in ("Type a file name.", "That's your original file. Pick another name.", "That's a folder. Pick a file name."):
            self.assertIn(msg, s)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.text)

    def test_overwrite_defaults_to_no(self):
        (self.dir / "broken.fixed.yaml").write_text("keep")
        written, s = self.flow(["enter", "enter", "enter", "esc"])
        self.assertIsNone(written)
        self.assertIn("broken.fixed.yaml exists. Overwrite?", s)
        self.assertEqual((self.dir / "broken.fixed.yaml").read_text(), "keep")

    def _fancy(self, fix):
        import argparse
        out = io.StringIO()
        args = argparse.Namespace(path=str(self.path), fix=fix, quiet=False, json=False, plain=False)
        code = vtp.run_fancy(args, False, out, iter([]), vtp.Caps(True, False, True, 100, 40))
        return code, vtp.strip_ansi(out.getvalue())

    def test_fix_flag_never_overwrites_the_original(self):
        code, s = self._fancy(str(self.path))
        self.assertEqual(code, 1)
        self.assertIn("--fix points at the original file. Nothing was written.", s)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.text)

    def test_unwritable_names_are_reported_not_crashed(self):
        written, s = self.flow(["enter"] + REPLACE("nodir/x.yaml") + ["enter", "esc"])
        self.assertIsNone(written)
        self.assertIn("Can't write x.yaml:", s)
        self.assertIn("Cancelled. Nothing was written.", s)
        code, s = self._fancy(str(self.dir / "nodir" / "x.yaml"))
        self.assertEqual(code, 1)
        self.assertIn("Can't write x.yaml:", s)

    def test_no_offer_without_testplan(self):
        doc = dict(self.res.doc)
        doc.pop("testPlan")
        res = self.res._replace(doc=doc)
        out = io.StringIO()
        self.assertIsNone(vtp.offer_repair(self.path, self.text, res, self.auto, out, iter([]), CAPS))
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()

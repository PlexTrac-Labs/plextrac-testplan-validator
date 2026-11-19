"""Screens: help, results panel, issues table, syntax error, can't open, nothing to pick."""
import tempfile
import unittest
from pathlib import Path

from tests.helpers import load_script, variant_text

vtp = load_script()
CAPS = vtp.Caps(True, True, True, 100, 40)


def plain(lines):
    return [vtp.strip_ansi(line) for line in lines]


class ScreenTest(unittest.TestCase):
    def test_results_panel(self):
        ok = vtp.run_checks(variant_text("ok"))
        rows = plain(vtp.results_panel("mini_ok.yaml", vtp.plan_stats(ok.doc), ok.report, 3, 0.04, CAPS))
        text = "\n".join(rows)
        self.assertTrue(all(vtp.cell_width(r) == 78 for r in rows))
        self.assertTrue(rows[0].startswith("╭─ mini_ok.yaml ─"))
        self.assertIn("█" * 34 + " 4", next(r for r in rows if "procedures" in r))
        self.assertIn("✔ YAML syntax   ✔ Structure   ✔ IDs   ✔ References   ✔ Content", text)
        self.assertIn(" READY TO IMPORT   10 objects · 16 links · 3 KB · 0.0s", text)
        bad = vtp.run_checks(variant_text("broken"))
        text = "\n".join(plain(vtp.results_panel("broken.yaml", vtp.plan_stats(bad.doc), bad.report, 3, 0.04, CAPS)))
        self.assertIn("✘ References", text)
        self.assertIn("✘ Content", text)
        self.assertIn(" NOT READY   2 errors · 1 warning", text)

    def test_issues_table(self):
        res = vtp.run_checks(variant_text("broken"))
        auto = vtp.auto_fixed(res.doc, res.report)
        rows = plain(vtp.issues_table(res.report, auto, False, CAPS))
        text = "\n".join(rows)
        self.assertTrue(all(vtp.cell_width(r) <= 78 for r in rows))
        self.assertEqual((text.count("▐auto▌"), text.count("by hand")), (2, 1))
        self.assertLess(text.index("reference.dangling"), text.index("reference.unused"))
        self.assertNotIn("reference.unused", "\n".join(plain(vtp.issues_table(res.report, auto, True, CAPS))))

    def test_syntax_error_screen(self):
        text = variant_text("syntax")
        res = vtp.run_checks(text)
        mark = res.parse_error.problem_mark
        rows = plain(vtp.syntax_error_screen("syntax.yaml", text, res.parse_error, CAPS))
        joined = "\n".join(rows)
        self.assertIn(f"✘ YAML syntax error · syntax.yaml · line {mark.line + 1}, column {mark.column + 1}", rows[0])
        gutter = f"❯ {mark.line + 1} │ "
        code = next(r for r in rows if gutter in r)
        caret = next(r for r in rows if "▲ mapping values are not allowed here" in r)
        self.assertEqual(caret.index("▲"), code.index(gutter) + len(gutter) + mark.column)
        self.assertIn('Tip: a value that contains ": " needs quotes, like shortName: "WSTG: draft"', joined)
        self.assertIn(" NOT READY   fix the line above and run it again", joined)

    def test_cannot_open_and_nothing_to_pick(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "OWASP_WSTG.yaml").write_text("x")
            text = "\n".join(plain(vtp.cannot_open_panel(str(Path(d) / "OWASP_WTSG.yaml"),
                                                         FileNotFoundError(2, "No such file or directory"), CAPS)))
            for s in ("✘ Can't open the file", "No file called OWASP_WTSG.yaml in", "Did you mean OWASP_WSTG.yaml?",
                      "Tip: run it without a file name to pick one from this folder."):
                self.assertIn(s, text)
            enc = "\n".join(plain(vtp.cannot_open_panel("latin1.yaml", UnicodeDecodeError("utf-8", b"\xe9", 0, 1, "x"), CAPS)))
            self.assertIn("latin1.yaml isn't UTF-8 text. Save it as UTF-8 and run it again.", enc)
            none = "\n".join(plain(vtp.nothing_to_pick_panel(Path(d) / "empty", CAPS)))
            for s in ("? Nothing to check here", "There are no .yaml files in empty/.",
                      "Point it at one:  python3 validate_test_plan.py path/to/plan.yaml"):
                self.assertIn(s, none)

    def test_help_and_cancel(self):
        rows = plain(vtp.help_screen(CAPS))
        text = "\n".join(rows)
        for s in ("plan.yaml", "--fix OUT", "--quiet", "--json", "--plain", "-h, --help",
                  "validate_test_plan.py [plan.yaml] [--fix OUT] [--quiet] [--json] [--plain]",
                  "exit codes   0 ready to import   1 errors found   2 couldn't read the file"):
            self.assertIn(s, text)
        self.assertTrue(all(vtp.cell_width(r) <= 78 for r in rows))
        self.assertEqual(vtp.strip_ansi(vtp.cancelled_line(CAPS)), "  ✘ Cancelled. Nothing was written.")
        self.assertEqual(vtp.strip_ansi(vtp.cancelled_line(CAPS, wrote=True)), "  ✘ Cancelled.")


if __name__ == "__main__":
    unittest.main()

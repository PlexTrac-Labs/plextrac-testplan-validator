"""Drawing primitives: boxes, pill badges, the banner and the spinner."""
import io
import time
import unittest

from tests.helpers import load_script

vtp = load_script()


class DrawTest(unittest.TestCase):
    def test_box_geometry(self):
        rows = [vtp.strip_ansi(r) for r in vtp.box([[("hello", "")], [("x" * 100, "")]],
                                                   [("OWASP_WSTG.yaml", "bold")], 40, vtp.STOPS[0], True)]
        self.assertTrue(all(vtp.cell_width(r) == 40 for r in rows))
        self.assertTrue(rows[0].startswith("╭─ OWASP_WSTG.yaml ─") and rows[0].endswith("╮"))
        self.assertEqual(rows[1], "│" + " " * 38 + "│")
        self.assertTrue(rows[3].endswith("…  │"))
        self.assertEqual(rows[-1], "╰" + "─" * 38 + "╯")

    def test_fit_pads_around_wide_characters(self):
        cut = vtp.fit([("ab🔧cd", "")], 4)
        self.assertEqual(vtp.line_width(cut), 4)
        self.assertTrue(vtp.render(cut, True).endswith("…"))

    def test_pill(self):
        self.assertEqual(vtp.strip_ansi(vtp.render(vtp.pill("auto", vtp.GREEN), True)), "▐auto▌")

    def test_banner(self):
        big = [vtp.strip_ansi(r) for r in vtp.banner(80, True)]
        self.assertEqual((len(big), big[0], big[-1]), (9, "", ""))
        self.assertEqual(big[1], "  " + "".join(vtp.FONT[c][0] for c in "TEST PLAN"))
        self.assertEqual(vtp.cell_width(big[1]), 72)
        self.assertTrue(big[7].endswith("v a l i d a t o r   ·   PlexTrac Runbooks V2"))
        self.assertEqual(vtp.cell_width(big[7]), 72)
        self.assertEqual([vtp.strip_ansi(r) for r in vtp.banner(73, True)],
                         ["  TEST PLAN validator · PlexTrac Runbooks V2"])

    def test_spinner_cleans_up(self):
        out = io.StringIO()
        with vtp.Spinner([("Validating x…", "")], out, True, interval=0.01):
            time.sleep(0.05)
        s = out.getvalue()
        self.assertIn("⠋", s)
        self.assertTrue(s.startswith("\x1b[?25l"))
        self.assertTrue(s.endswith("\r\x1b[2K\x1b[?25h"))


if __name__ == "__main__":
    unittest.main()

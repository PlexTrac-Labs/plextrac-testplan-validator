"""The command line end to end: plain fallbacks, and the fancy mode in a real (pseudo) terminal."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PtySession, load_script, run_cli, variant_text

vtp = load_script()


class CliTest(unittest.TestCase):
    def test_no_path_without_a_terminal(self):
        run = run_cli([], {})
        self.assertEqual(run.code, 2)
        self.assertIn("the following arguments are required: path", run.stderr)

    def test_plain_help_lists_plain_flag(self):
        run = run_cli(["--help"], {})
        self.assertEqual(run.code, 0)
        self.assertIn("--plain", run.stdout)

    def test_age_text(self):
        self.assertEqual([vtp.age_text(s) for s in (30, 120, 3600, 3 * 86400)],
                         ["just now", "2 minutes ago", "1 hour ago", "3 days ago"])


@unittest.skipIf(sys.platform == "win32", "needs a POSIX pseudo-terminal")
class TerminalTest(unittest.TestCase):
    def folder(self, **files):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        for name, variant in files.items():
            (d / f"{name}.yaml").write_text(variant_text(variant), encoding="utf-8")
        return d

    def test_picker_then_results(self):
        d = self.folder(broken="broken", mini_ok="ok")
        s = PtySession([], d)
        s.expect("Which test plan?")
        s.send("\x1b[B\r")
        s.expect("READY TO IMPORT")
        self.assertEqual(s.wait(), 0)

    def test_esc_in_picker(self):
        s = PtySession([], self.folder(mini_ok="ok"))
        s.expect("Which test plan?")
        s.send("\x1b")
        self.assertEqual(s.wait(), 2)

    def test_repair_end_to_end(self):
        d = self.folder(broken="broken")
        s = PtySession(["broken.yaml"], d)
        s.expect("Repair them and save a copy?")
        s.send("\r")
        s.expect("Save as")
        s.send("\r")
        s.expect("re-checked")
        self.assertEqual(s.wait(), 1)
        self.assertTrue((d / "broken.fixed.yaml").exists())

    def test_ctrl_c_restores_terminal(self):
        d = self.folder(broken="broken")
        s = PtySession(["broken.yaml"], d)
        s.expect("Repair them and save a copy?")
        s.send("\x03")
        self.assertEqual(s.wait(), 130)
        self.assertIn("\x1b[?25h", s.raw)
        self.assertIn("Cancelled. Nothing was written.", vtp.strip_ansi(s.raw))
        self.assertFalse((d / "broken.fixed.yaml").exists())

    def test_narrow_terminal_and_plain_flag_are_plain(self):
        for args, cols in ((["mini_ok.yaml"], 50), (["--plain", "mini_ok.yaml"], 100)):
            s = PtySession(args, self.folder(mini_ok="ok"), cols=cols)
            s.expect("OK to import")
            self.assertEqual(s.wait(), 0)
            self.assertNotIn("╭", s.raw)


if __name__ == "__main__":
    unittest.main()

"""Terminal capability detection, colour helpers and text measuring."""
import io
import unittest

from tests.helpers import load_script

vtp = load_script()


class FakeStream(io.StringIO):
    def __init__(self, tty=True, encoding="utf-8"):
        super().__init__()
        self._tty, self._enc = tty, encoding

    def isatty(self):
        return self._tty

    @property
    def encoding(self):
        return self._enc


def detect(**kw):
    args = dict(plain=False, json_out=False, env={"COLORTERM": "truecolor"}, stdout=FakeStream(),
                stdin=FakeStream(), platform="darwin", size=(100, 40), enable_vt=lambda: True)
    args.update(kw)
    return vtp.detect_mode(**args)


class TermTest(unittest.TestCase):
    def test_detect_mode(self):
        self.assertEqual(detect(), vtp.Caps(True, True, True, 100, 40))
        for kw in (dict(stdout=FakeStream(False)), dict(json_out=True), dict(plain=True),
                   dict(env={"NO_COLOR": "1"}), dict(env={"TERM": "dumb"}),
                   dict(stdout=FakeStream(True, "cp1252")), dict(size=(59, 40)),
                   dict(platform="win32", env={}),
                   dict(platform="win32", env={"WT_SESSION": "1"}, enable_vt=lambda: False)):
            self.assertFalse(detect(**kw).fancy, kw)
        for kw in (dict(env={"NO_COLOR": ""}), dict(size=(60, 40)),
                   dict(platform="win32", env={"WT_SESSION": "1"}),
                   dict(platform="win32", env={"TERM_PROGRAM": "vscode"})):
            self.assertTrue(detect(**kw).fancy, kw)
        piped_in = detect(stdin=FakeStream(False))
        self.assertTrue(piped_in.fancy)
        self.assertFalse(piped_in.interactive)
        self.assertFalse(detect(env={}).truecolor)
        self.assertTrue(detect(env={"WT_SESSION": "1"}).truecolor)

    def test_vt_only_checked_on_windows_terminals(self):
        calls = []
        detect(enable_vt=lambda: calls.append(1) or True)
        detect(platform="win32", env={}, enable_vt=lambda: calls.append(1) or True)
        self.assertEqual(calls, [])

    def test_colour(self):
        self.assertEqual((vtp.gradient(vtp.STOPS, 0), vtp.gradient(vtp.STOPS, 1)), ("#22d3ee", "#fb7185"))
        self.assertEqual(vtp.gradient(("#000000", "#ffffff"), 0.5), "#808080")
        self.assertEqual(vtp.shade("#ffffff", 0.45), "#737373")
        self.assertEqual([vtp.xterm256(c) for c in ("#ff5faf", "#000000", "#ffffff", "#22d3ee")], [205, 16, 231, 45])
        self.assertEqual(vtp.style_sgr("bold fg:#ff5faf", True), "\x1b[1;38;2;255;95;175m")
        self.assertEqual(vtp.style_sgr("dim fg:#ff5faf", False), "\x1b[2;38;5;205m")
        self.assertEqual(vtp.style_sgr("", True), "")

    def test_measuring(self):
        self.assertEqual([vtp.cell_width(s) for s in ("abc", "🔧", "▐auto▌", "✔︎ ok")], [3, 2, 6, 4])
        self.assertEqual(vtp.wrap_cells("aaa bbb ccc", 7), ["aaa bbb", "ccc"])
        self.assertEqual(vtp.wrap_cells("x" * 10, 4), ["xxxx", "xxxx", "xx"])
        self.assertEqual(vtp.strip_ansi("\x1b[1;38;2;1;2;3mhi\x1b[0m\x1b[?25h"), "hi")


if __name__ == "__main__":
    unittest.main()

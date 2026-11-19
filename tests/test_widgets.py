"""Key decoding and the choose / confirm / prompt widgets, driven by scripted keys."""
import io
import unittest

from tests.helpers import load_script

vtp = load_script()


class WidgetTest(unittest.TestCase):
    def test_decode_key(self):
        for seq, name in {"\x1b[A": "up", "\x1bOB": "down", "\x1b[C": "right", "\x1b[D": "left",
                          "\x1b[H": "home", "\x1b[1~": "home", "\x1b[F": "end", "\x1b[4~": "end",
                          "\x1b[3~": "delete", "\x1b": "esc", "\r": "enter", "\n": "enter",
                          "\x7f": "backspace", "\x08": "backspace", "\x03": "ctrl-c",
                          "a": "a", "é": "é", "\x1b[99~": "unknown"}.items():
            self.assertEqual(vtp.decode_key(seq), name, repr(seq))
        self.assertEqual([vtp.decode_windows_key(p, c) for p, c in (("\xe0", "H"), ("\x00", "P"), ("\xe0", "S"))],
                         ["up", "down", "delete"])

    def test_choose(self):
        opts = [[(f"plan{i}.yaml", "")] for i in range(30)]
        t = [("Which?", "")]
        run = lambda options, keys, rows=10: vtp.choose(options, t, io.StringIO(), iter(keys), True, rows)
        self.assertEqual(run(opts[:3], ["down", "down", "enter"]), 2)
        self.assertEqual(run(opts[:3], ["up", "enter"]), 0)
        self.assertIsNone(run(opts[:3], ["esc"]))
        self.assertEqual(run(opts, ["down"] * 12 + ["enter"], rows=5), 12)
        with self.assertRaises(KeyboardInterrupt):
            run(opts, ["ctrl-c"])

    def test_choose_restores_cursor_and_erases_itself(self):
        out = io.StringIO()
        vtp.choose([[("a.yaml", "")]], [("Which?", "")], out, iter(["enter"]), True, 5)
        self.assertTrue(out.getvalue().startswith("\x1b[?25l"))
        self.assertTrue(out.getvalue().endswith("\x1b[J\x1b[?25h"))

    def test_confirm(self):
        q = [("Repair them?", "")]
        ask = lambda default, keys: vtp.confirm(q, default, io.StringIO(), iter(keys), True)
        self.assertEqual([ask(True, ["enter"]), ask(False, ["enter"]), ask(True, ["n"]), ask(False, ["Y"]),
                          ask(True, ["esc"])], [True, False, False, True, None])

    def test_prompt_editing(self):
        p = [("Save as", "")]
        edit = lambda initial, keys: vtp.prompt(p, initial, io.StringIO(), iter(keys), True)
        self.assertEqual(edit("a.fixed.yaml", ["enter"]), "a.fixed.yaml")
        self.assertEqual(edit("a.fixed.yaml", ["home", "delete", "b", "end", "backspace", "enter"]), "b.fixed.yam")
        self.assertEqual(edit("ab", ["left", "x", "enter"]), "axb")
        self.assertIsNone(edit("a", ["esc"]))
        with self.assertRaises(KeyboardInterrupt):
            edit("a", ["ctrl-c"])

    def test_running_out_of_keys_counts_as_esc(self):
        self.assertIsNone(vtp.confirm([("Sure?", "")], True, io.StringIO(), iter([]), True))
        self.assertIsNone(vtp.prompt([("Name", "")], "x", io.StringIO(), iter([]), True))


if __name__ == "__main__":
    unittest.main()

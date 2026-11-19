"""Plain and JSON output must stay exactly what the script printed before the graphics work."""
import unittest

from tests.helpers import GOLDEN, format_run, golden_cases, run_cli


class PlainGoldenTest(unittest.TestCase):
    def test_plain_output_matches_golden(self):
        for case in golden_cases():
            with self.subTest(case=case.name):
                golden = GOLDEN / f"{case.name}.txt"
                self.assertTrue(golden.exists(), f"missing golden file {golden.name}")
                run = run_cli(case.args, case.files, case.read_after)
                self.assertEqual(format_run(run), golden.read_text(encoding="utf-8"))
                if case.read_after:
                    self.assertEqual(run.after, (GOLDEN / f"{case.name}.out.yaml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

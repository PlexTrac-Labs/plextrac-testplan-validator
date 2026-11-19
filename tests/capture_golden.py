"""Record the script's current plain and JSON output as golden files.

Run from the repo root, only when an output change is intended:
    python3 -m tests.capture_golden
"""
from tests.helpers import GOLDEN, format_run, golden_cases, run_cli


def main() -> None:
    GOLDEN.mkdir(exist_ok=True)
    for case in golden_cases():
        run = run_cli(case.args, case.files, case.read_after)
        (GOLDEN / f"{case.name}.txt").write_text(format_run(run), encoding="utf-8")
        if case.read_after:
            (GOLDEN / f"{case.name}.out.yaml").write_text(run.after or "", encoding="utf-8")
        print("wrote", case.name, "exit", run.code)


if __name__ == "__main__":
    main()

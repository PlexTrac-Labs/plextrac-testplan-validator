# Manual checklist: terminal graphics

The automated tests cover the logic and drive the real script through a pseudo-terminal on macOS
and Linux. This list covers what only a person at a keyboard can judge: how it looks, and how it
feels with real keys. Allow about 15 minutes.

Run each part in the place it names. Note anything that looks wrong, with a screenshot.

## Setup

From the folder that holds the plans (for example `validate-test-plan`), make a broken copy of the
sample plan to practise the repair on:

```bash
python3 -c "import sys; sys.path.insert(0, 'plextrac-testplan-validator'); from tests.helpers import variant_text; open('broken.yaml', 'w').write(variant_text('broken'))"
```

Below, `vtp` stands for `python3 plextrac-testplan-validator/validate_test_plan.py`.
Check the exit code after a run with `echo $?` (macOS, Linux) or `echo $LASTEXITCODE` (PowerShell).

## A. Mac (iTerm2) and the Linux container

To open the Linux container (Python 3.8), from the plans folder:

```bash
colima start            # if it isn't running
docker run -it --rm -v "$PWD":/w -w /w python:3.8-slim bash
pip install -q pyyaml
```

Then go through the list once on the Mac and once in the container.

| # | Do this | Expect |
|---|---|---|
| 1 | `vtp OWASP_MASTG.yaml` | Gradient TEST PLAN logo, a summary box with bars, five green ticks, **READY TO IMPORT**. Exit 0. |
| 2 | `vtp` (no file name) | "found N test plans", then a menu. ↑/↓ move the `❯`, Enter checks that file. |
| 3 | `vtp`, then Esc | Menu disappears, "✘ Cancelled. Nothing was written." Exit 2. |
| 4 | `vtp broken.yaml` | Summary with red ✘ for References and Content, an issues table with two green `▐auto▌` badges and one `by hand`, then "🔧 2 of 3 problems can be repaired automatically". |
| 5 | Continue from 4: Enter, then at "Save as" change the name to `broken.v2.yaml` (←, Backspace, typing) and press Enter | A "Repaired copy · broken.v2.yaml" box listing what changed, then a green "re-checked" box with READY TO IMPORT. `broken.yaml` is unchanged. Exit 1. |
| 6 | `vtp broken.yaml`, Enter, then Enter at "Save as" twice in a row (run it two times so `broken.fixed.yaml` exists) | Second time: "broken.fixed.yaml exists. Overwrite? (y/N)". Enter keeps the old file and asks for a name again. Esc then cancels. |
| 7 | `vtp broken.yaml`, Enter, type `broken.yaml` as the name | "✘ That's your original file. Pick another name." |
| 8 | Ctrl+C at the menu, at "Repair them…", at "Save as", and while it says "Validating…" on a big plan | "✘ Cancelled." Exit 130. Afterwards the cursor is visible and typing shows normally. |
| 9 | `vtp OWASP_MASTG.yaml \| cat` | Plain text (the old format), no colour codes, no boxes. |
| 10 | `NO_COLOR=1 vtp OWASP_MASTG.yaml` | Plain text. |
| 11 | Make the window narrower than 60 columns, run `vtp OWASP_MASTG.yaml` | Plain text. Between 60 and 73 columns: a one-line title instead of the big logo, boxes intact. |
| 12 | `printf 'methodologies:\n  - shortName: A: B\n' > syntax.yaml` then `vtp syntax.yaml` | Red "YAML syntax error" box, the bad line marked with `❯`, a `▲` under the problem, the quoting tip. Exit 1. |
| 13 | `vtp OWASP_MSTG.yaml` (typo) | "Can't open the file", "Did you mean OWASP_MASTG.yaml?". Exit 2. |
| 14 | `vtp -h` | Logo, usage box, options, exit codes. |
| 15 | `vtp broken.yaml --json` | JSON only, no graphics. |

## B. Windows (coworker)

Copy the script and the two OWASP plans into one folder. Python 3.8 or newer and `pip install pyyaml`
are needed. Make `broken.yaml` with the setup command above (use `py` instead of `python3`).

**Windows Terminal, and the VS Code terminal.** Run rows 1 to 8, 9 (`| more` instead of `| cat`),
12 to 15. Expect the same as on the Mac: colours, boxes, arrow keys and Ctrl+C all working.

**The classic console** (a cmd.exe or PowerShell window that is *not* Windows Terminal):

| Do this | Expect |
|---|---|
| `py validate_test_plan.py OWASP_MASTG.yaml` | Plain text only: no boxes, no question marks or squares where symbols would be. |
| `py validate_test_plan.py` | "the following arguments are required: path" (no menu here). Exit 2. |
| `py validate_test_plan.py broken.yaml` | Plain text errors, no repair question. |

Please report: Windows version, which window, `py --version`, and a screenshot of anything that
looks garbled.

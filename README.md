# PlexTrac Test Plan Validator

Pre-flight checks for PlexTrac Runbooks (V2) test plan YAML files, so you find out why an import will fail before you upload it.

The import UI returns limited feedback on failure, which otherwise means digging through Grafana logs to find out that an ID was one character off. This script catches the common causes locally in about a second.

## Requirements

Python 3.8 or newer and PyYAML. No other dependencies.

```bash
pip3 install pyyaml
```

## Usage

```bash
python3 validate_test_plan.py                            # pick a plan from this folder
python3 validate_test_plan.py plan.yaml                  # check a file
python3 validate_test_plan.py plan.yaml --json           # machine-readable output
python3 validate_test_plan.py plan.yaml --quiet          # errors only, no warnings
python3 validate_test_plan.py plan.yaml --fix out.yaml   # write a repaired copy
python3 validate_test_plan.py plan.yaml --plain          # plain text, even in a terminal
```

In a terminal the validator draws its results: a banner, a summary box with the object counts and a pass or fail for each group of checks, and a table of problems marked `auto` (the repair fixes it) or `by hand`. Run it without a file name to pick one from the current folder with the arrow keys.

When the output goes to a pipe or a file, or with `--plain` or `--json`, it prints the plain text shown under [Example](#example), unchanged from earlier versions, so scripts keep working. Setting `NO_COLOR=1`, or a terminal narrower than 60 columns, also gives plain text. On Windows the graphics appear in Windows Terminal and the VS Code terminal; the classic console window gets plain text.

| Exit code | Meaning |
|---|---|
| `0` | No errors (warnings allowed) |
| `1` | Errors found, including YAML syntax errors |
| `2` | The file couldn't be read, there was nothing to pick, or the picker was cancelled |
| `130` | Cancelled with Ctrl+C |

Errors block the import. Warnings do not, but are usually worth a look.

## Example

```
$ python3 validate_test_plan.py OWASP_WSTG.yaml
OWASP_WSTG.yaml  (115 objects, 789 KB)
  ERROR  reference.dangling  [tactics[0] WSTG-SESS]
         methodologyIds 'cm5o15i3100010hmp9oqddvti' is not defined in this file.
         The import inserts a link to a methodology row that does not exist and
         fails on a foreign key constraint.
  2 error(s), 0 warning(s)
```

```
$ python3 validate_test_plan.py OWASP_MASTG.yaml
OWASP_MASTG.yaml  (213 objects, 711 KB)
  0 error(s), 0 warning(s)
  OK to import
```

## What it checks

**File and syntax**

- YAML parse errors, reported with line and column
- Stray YAML anchors. Only the `testPlan` / `runbook` anchor is valid. Generators that emit aliases by default anchor every node, and the import parser rejects those files
- Tabs and byte order marks

**Structure**

- All seven top-level sections present: `methodologies`, `tactics`, `techniques`, `repositories`, `procedures`, `testPlan`, `runbook`
- Required fields present on every object, unexpected fields flagged
- `executionSteps` shape on each procedure
- `runbook` is a genuine YAML alias of `testPlan`, not a duplicated copy

**IDs**

- CUID format, a lowercase `c` followed by 24 lowercase alphanumerics
- No duplicate IDs across any section

**References**

Every cross-reference resolves inside the file: `methodologyIds`, `tacticIds`, `techniqueIds`, `repositoryId` and `testPlan.procedureIds`. A reference to an object that is not in the file is what produces foreign key errors like `runbook_tactic_to_methodology_methodology_id_fkey` on import.

**Content warnings**

- Procedures defined but missing from `testPlan.procedureIds`, which import but never appear in the plan
- Duplicate `shortName` values
- Empty descriptions
- Non-empty `tags` arrays, which must be empty at import time and applied through the UI afterwards

## Repairing a file

```bash
python3 validate_test_plan.py broken.yaml --fix fixed.yaml
```

Writes a new file and leaves the original untouched. It performs mechanical repairs only: dropping dangling reference IDs and emptying tag arrays. Writing the file fresh also removes stray YAML anchors, tab characters and byte order marks, and restores `runbook` as an alias of `testPlan`. It will not invent IDs or restructure content, so anything else reported needs fixing by hand.

In a terminal you don't need `--fix`. When some of the problems can be repaired, the validator offers to save a repaired copy:

1. It asks before writing anything (Enter means yes).
2. It suggests `<name>.fixed.yaml` next to the original. Edit the name with the arrow keys, Backspace and Delete.
3. It refuses to write over the original file, and asks before replacing any other existing file (Enter means no).
4. It shows what changed, object by object, then checks the repaired copy and says whether it's ready to import.

The exit code still describes the original file.

## Known exporter issue

If a test plan has tactics belonging to more than one methodology, the export writes the link to the second methodology but not the methodology itself. The resulting file cannot be imported anywhere and fails on a foreign key constraint. Running `--fix` on such an export drops the unresolvable link and produces an importable file.

## Development

The tests use the standard library only. From this folder:

```bash
python3 -m unittest discover -s tests -t .
```

They compare the plain and JSON output against recorded copies in `tests/golden/`, so any change to that output shows up as a failure. `tests/MANUAL_CHECKLIST.md` lists the hands-on checks for macOS, Linux and Windows.

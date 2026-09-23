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
python3 validate_test_plan.py plan.yaml                  # check a file
python3 validate_test_plan.py plan.yaml --json           # machine-readable output
python3 validate_test_plan.py plan.yaml --quiet          # errors only, no warnings
python3 validate_test_plan.py plan.yaml --fix out.yaml   # write a repaired copy
```

Exit codes: `0` clean, `1` errors found, `2` file unreadable.

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

Writes a new file and leaves the original untouched. It performs mechanical repairs only: dropping dangling reference IDs and emptying tag arrays. It will not invent IDs or restructure content, so anything else reported needs fixing by hand.

## Known exporter issue

If a test plan has tactics belonging to more than one methodology, the export writes the link to the second methodology but not the methodology itself. The resulting file cannot be imported anywhere and fails on a foreign key constraint. Running `--fix` on such an export drops the unresolvable link and produces an importable file.

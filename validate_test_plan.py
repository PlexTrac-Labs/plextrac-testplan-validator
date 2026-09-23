#!/usr/bin/env python3
"""
validate_test_plan.py - pre-flight check for PlexTrac Runbooks (V2) test plan YAML.

Catches the failures that produce unhelpful UI errors, before you upload:

  * YAML that the API's parser rejects (stray anchors, indentation)
  * dangling references that fail on a DB foreign key constraint
  * malformed or duplicate CUIDs
  * non-empty tag arrays
  * a runbook key that is not an alias of testPlan

The PlexTrac OpenAPI spec documents POST /api/v1/import/runbook but publishes no
request schema, so these rules come from a known-good export plus observed
import failures. Treat ERRORs as blocking and WARNs as worth a look.

Usage:
    python3 validate_test_plan.py plan.yaml
    python3 validate_test_plan.py plan.yaml --json
    python3 validate_test_plan.py plan.yaml --fix fixed.yaml

Exit codes: 0 clean (warnings allowed), 1 errors found, 2 could not read file.
Requires PyYAML only.
"""
import argparse
import json
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required:  pip install pyyaml")

CUID = re.compile(r"^c[a-z0-9]{24}$")
TOP_KEYS = ["methodologies", "tactics", "techniques", "repositories",
            "procedures", "testPlan", "runbook"]

REQUIRED = {
    "methodologies": {"id", "name", "shortName", "description", "origin",
                      "isEditable", "sourceId", "sourceKey", "sourceValue", "tags"},
    "tactics": {"id", "name", "shortName", "description", "origin", "isEditable",
                "sourceId", "sourceKey", "sourceValue", "methodologyIds", "tags"},
    "techniques": {"id", "name", "shortName", "description", "origin", "isEditable",
                   "sourceId", "sourceKey", "sourceValue", "tacticIds", "tags"},
    "repositories": {"id", "name", "shortName", "description", "type", "origin",
                     "isEditable"},
    "procedures": {"id", "name", "shortName", "description", "repositoryId",
                   "origin", "isEditable", "sourceId", "sourceKey", "sourceValue",
                   "executionSteps", "techniqueIds", "tags"},
}
TEST_PLAN_KEYS = {"id", "title", "description", "type", "origin", "isEditable",
                  "procedureIds", "tags"}


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, check, msg, where=None):
        self.errors.append({"check": check, "message": msg, "where": where})

    def warn(self, check, msg, where=None):
        self.warnings.append({"check": check, "message": msg, "where": where})


def collect_anchors(text):
    """Anchor names actually used as YAML anchors, not '&amp;' inside content."""
    names = []
    try:
        for ev in yaml.parse(text):
            anchor = getattr(ev, "anchor", None)
            if anchor and not isinstance(ev, yaml.AliasEvent):
                names.append(anchor)
    except yaml.YAMLError:
        return None
    return names


def check_raw_text(text, rep):
    """Checks that must run on the raw file, before the YAML is parsed."""
    anchors = collect_anchors(text)
    if anchors is None:
        return  # a parse failure is reported separately
    stray = sorted(set(a for a in anchors if a != "ref_0"))
    if stray:
        rep.error("yaml.anchors",
                  f"{len(stray)} YAML anchor(s) other than ref_0: "
                  f"{', '.join(stray[:5])}{'...' if len(stray) > 5 else ''}. "
                  "The import parser rejects anchored block mappings. Most YAML "
                  "libraries add these automatically when alias output is enabled.")

    if not re.search(r"^testPlan:\s*&ref_0\s*$", text, re.M):
        rep.warn("yaml.anchor_name",
                 "testPlan is not anchored as '&ref_0'. Exports use this form.")
    if not re.search(r"^runbook:\s*\*ref_0\s*$", text, re.M):
        rep.warn("yaml.alias_name",
                 "runbook is not the alias '*ref_0'. Exports use this form.")
    if "\t" in text:
        rep.error("yaml.tabs", "File contains tab characters, which YAML forbids "
                               "for indentation.")
    if text.startswith("\ufeff"):
        rep.error("yaml.bom", "File starts with a UTF-8 BOM. Save without it.")


def check_structure(doc, rep):
    if not isinstance(doc, dict):
        rep.error("schema.root", "Top level of the file is not a mapping.")
        return False
    missing = [k for k in TOP_KEYS if k not in doc]
    if missing:
        rep.error("schema.sections", f"Missing top-level section(s): {', '.join(missing)}")
    extra = [k for k in doc if k not in TOP_KEYS]
    if extra:
        rep.warn("schema.sections", f"Unexpected top-level key(s): {', '.join(extra)}")
    for k in ["methodologies", "tactics", "techniques", "repositories", "procedures"]:
        if k in doc and not isinstance(doc[k], list):
            rep.error("schema.sections", f"'{k}' should be a list.")
    return not missing


def check_objects(doc, rep):
    seen = {}
    for section, required in REQUIRED.items():
        for i, obj in enumerate(doc.get(section) or []):
            where = f"{section}[{i}]"
            if not isinstance(obj, dict):
                rep.error("schema.object", "Entry is not a mapping.", where)
                continue
            label = obj.get("shortName") or obj.get("name") or where
            where = f"{section}[{i}] {label}"

            for key in sorted(required - set(obj)):
                rep.error("schema.field", f"Missing required field '{key}'.", where)
            for key in sorted(set(obj) - required):
                rep.warn("schema.field", f"Unexpected field '{key}'.", where)

            oid = obj.get("id")
            if oid is not None:
                if not isinstance(oid, str) or not CUID.match(oid):
                    rep.error("id.format",
                              f"id '{oid}' is not a CUID (c + 24 lowercase "
                              "alphanumerics). Non-conforming ids fail the import.",
                              where)
                elif oid in seen:
                    rep.error("id.duplicate",
                              f"id '{oid}' already used by {seen[oid]}.", where)
                else:
                    seen[oid] = where

            if "tags" in required and obj.get("tags") != []:
                rep.error("tags.nonempty",
                          f"tags must be an empty list at import time, found "
                          f"{obj.get('tags')!r}.", where)

            if section == "procedures":
                steps = obj.get("executionSteps")
                if not isinstance(steps, list) or not steps:
                    rep.error("schema.steps",
                              "executionSteps must be a non-empty list.", where)
                else:
                    for j, step in enumerate(steps):
                        if not isinstance(step, dict):
                            rep.error("schema.steps", f"step {j} is not a mapping.", where)
                            continue
                        if "description" not in step:
                            rep.error("schema.steps",
                                      f"step {j} has no description.", where)
                        for key in set(step) - {"description", "successCriteria"}:
                            rep.warn("schema.steps",
                                     f"step {j} has unexpected field '{key}'.", where)

    tp = doc.get("testPlan")
    if isinstance(tp, dict):
        for key in sorted(TEST_PLAN_KEYS - set(tp)):
            rep.error("schema.field", f"testPlan is missing '{key}'.", "testPlan")
        for key in sorted(set(tp) - TEST_PLAN_KEYS):
            rep.warn("schema.field", f"testPlan has unexpected field '{key}'.", "testPlan")
        if tp.get("tags") != []:
            rep.error("tags.nonempty", "testPlan tags must be an empty list.", "testPlan")
        if isinstance(tp.get("id"), str) and not CUID.match(tp["id"]):
            rep.error("id.format", f"testPlan id '{tp['id']}' is not a CUID.", "testPlan")
    else:
        rep.error("schema.sections", "testPlan is missing or not a mapping.")

    if doc.get("runbook") is not tp:
        rep.error("runbook.alias",
                  "runbook is not the same node as testPlan. It must be a YAML "
                  "alias (runbook: *ref_0), not a copy.", "runbook")


def check_references(doc, rep):
    def ids(section):
        return {o["id"] for o in (doc.get(section) or [])
                if isinstance(o, dict) and isinstance(o.get("id"), str)}

    meth, tac = ids("methodologies"), ids("tactics")
    tech, repo = ids("techniques"), ids("repositories")
    proc = ids("procedures")

    def link(section, field, pool, pool_name):
        for i, obj in enumerate(doc.get(section) or []):
            if not isinstance(obj, dict):
                continue
            where = f"{section}[{i}] {obj.get('shortName') or obj.get('name') or ''}".strip()
            vals = obj.get(field)
            vals = vals if isinstance(vals, list) else ([vals] if vals else [])
            for v in vals:
                if v not in pool:
                    rep.error("reference.dangling",
                              f"{field} '{v}' is not defined in this file. The import "
                              f"inserts a link to a {pool_name} row that does not "
                              "exist and fails on a foreign key constraint.", where)
            if not vals and field in ("methodologyIds", "tacticIds", "techniqueIds"):
                rep.warn("reference.orphan", f"{field} is empty.", where)

    link("tactics", "methodologyIds", meth, "methodology")
    link("techniques", "tacticIds", tac, "tactic")
    link("procedures", "techniqueIds", tech, "technique")
    link("procedures", "repositoryId", repo, "repository")

    tp = doc.get("testPlan")
    if isinstance(tp, dict):
        listed = tp.get("procedureIds") or []
        for pid in listed:
            if pid not in proc:
                rep.error("reference.dangling",
                          f"testPlan.procedureIds contains '{pid}', which is not a "
                          "procedure in this file.", "testPlan")
        missing = proc - set(listed)
        if missing:
            rep.warn("reference.unused",
                     f"{len(missing)} procedure(s) defined but not listed in "
                     "testPlan.procedureIds. They import but will not appear in the "
                     "test plan.", "testPlan")
        if len(listed) != len(set(listed)):
            rep.warn("reference.duplicate",
                     "testPlan.procedureIds contains duplicates.", "testPlan")


def check_content(doc, rep):
    for section in ("methodologies", "tactics", "techniques", "procedures"):
        shorts = {}
        for obj in doc.get(section) or []:
            if not isinstance(obj, dict):
                continue
            sn = obj.get("shortName")
            if sn:
                shorts.setdefault(sn, []).append(obj.get("name"))
        for sn, names in shorts.items():
            if len(names) > 1:
                rep.warn("content.duplicate_shortname",
                         f"shortName '{sn}' used {len(names)} times in {section}.")
    for i, p in enumerate(doc.get("procedures") or []):
        if isinstance(p, dict) and not (p.get("description") or "").strip():
            rep.warn("content.empty",
                     "Procedure has an empty description.",
                     f"procedures[{i}] {p.get('shortName') or ''}".strip())


def autofix(doc, text, rep):
    """Only safe, mechanical repairs: drop dangling links, empty tag arrays."""
    fixes = []

    def ids(section):
        return {o["id"] for o in (doc.get(section) or []) if isinstance(o, dict)}

    pools = {"methodologyIds": ids("methodologies"), "tacticIds": ids("tactics"),
             "techniqueIds": ids("techniques")}
    for section, field in [("tactics", "methodologyIds"), ("techniques", "tacticIds"),
                           ("procedures", "techniqueIds")]:
        for obj in doc.get(section) or []:
            if not isinstance(obj, dict) or not isinstance(obj.get(field), list):
                continue
            kept = [v for v in obj[field] if v in pools[field]]
            if len(kept) != len(obj[field]):
                dropped = [v for v in obj[field] if v not in pools[field]]
                fixes.append(f"{section} '{obj.get('shortName')}': dropped "
                             f"{field} {dropped}")
                obj[field] = kept

    for section in ("methodologies", "tactics", "techniques", "procedures"):
        for obj in doc.get(section) or []:
            if isinstance(obj, dict) and obj.get("tags") not in (None, []):
                fixes.append(f"{section} '{obj.get('shortName')}': emptied tags")
                obj["tags"] = []
    tp = doc.get("testPlan")
    if isinstance(tp, dict) and tp.get("tags") not in (None, []):
        fixes.append("testPlan: emptied tags")
        tp["tags"] = []
    return fixes


def dump(doc):
    class D(yaml.SafeDumper):
        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow, False)

        def ignore_aliases(self, data):
            return True

    D.add_representer(str, lambda dd, s: dd.represent_scalar(
        "tag:yaml.org,2002:str", s, style=">" if len(s) > 120 else None))
    body = {k: v for k, v in doc.items() if k != "runbook"}
    out = yaml.dump(body, Dumper=D, sort_keys=False, width=78,
                    allow_unicode=True, default_flow_style=False)
    out = re.sub(r"^testPlan:$", "testPlan: &ref_0", out, count=1, flags=re.M)
    if not out.endswith("\n"):
        out += "\n"
    return out + "runbook: *ref_0\n"


def main():
    ap = argparse.ArgumentParser(description="Validate a PlexTrac Runbooks V2 "
                                             "test plan YAML before importing it.")
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--fix", metavar="OUT", help="write a repaired copy to OUT")
    ap.add_argument("--quiet", action="store_true", help="errors only")
    args = ap.parse_args()

    rep = Report()
    try:
        text = open(args.path, encoding="utf-8").read()
    except OSError as e:
        sys.exit(f"cannot read {args.path}: {e}")

    check_raw_text(text, rep)

    doc = None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"line {mark.line + 1}, column {mark.column + 1}" if mark else None
        rep.error("yaml.parse", str(getattr(e, "problem", e)).strip(), where)

    if doc is not None and check_structure(doc, rep):
        check_objects(doc, rep)
        check_references(doc, rep)
        check_content(doc, rep)

    fixes = []
    if args.fix and doc is not None:
        fixes = autofix(doc, text, rep)
        open(args.fix, "w", encoding="utf-8").write(dump(doc))

    counts = {"errors": len(rep.errors), "warnings": len(rep.warnings)}
    if args.json:
        print(json.dumps({"file": args.path, **counts, "error_list": rep.errors,
                          "warning_list": rep.warnings, "fixes": fixes}, indent=2))
    else:
        obj_count = sum(len(doc.get(k) or []) for k in
                        ("methodologies", "tactics", "techniques", "repositories",
                         "procedures")) if isinstance(doc, dict) else 0
        print(f"{args.path}  ({obj_count} objects, {len(text) // 1024} KB)")
        for item in rep.errors:
            loc = f"  [{item['where']}]" if item["where"] else ""
            print(f"  ERROR  {item['check']}{loc}\n         {item['message']}")
        if not args.quiet:
            for item in rep.warnings:
                loc = f"  [{item['where']}]" if item["where"] else ""
                print(f"  WARN   {item['check']}{loc}\n         {item['message']}")
        if fixes:
            print(f"  fixed {len(fixes)} item(s), written to {args.fix}:")
            for f in fixes[:10]:
                print(f"         {f}")
        print(f"  {counts['errors']} error(s), {counts['warnings']} warning(s)")
        if not counts["errors"]:
            print("  OK to import")

    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()

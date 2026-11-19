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
import functools
import json
import re
import sys
import unicodedata
from typing import Any, Callable, Dict, List, Mapping, NamedTuple, Optional, Sequence, Set, Tuple

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


IssueKey = Tuple[str, str, Optional[str]]
SECTIONS = ("methodologies", "tactics", "techniques", "repositories", "procedures")
LABELS = ("YAML syntax", "Structure", "IDs", "References", "Content")
_GROUP_PREFIXES = (("yaml.", "YAML syntax"), ("schema.", "Structure"), ("id.", "IDs"),
                   ("reference.", "References"), ("runbook.", "References"),
                   ("tags.", "Content"), ("content.", "Content"))


def issue_key(item: dict) -> IssueKey:
    """Identity of one reported issue, for comparing two reports."""
    return (item["check"], item["message"], item["where"])


def group_of(check: str) -> str:
    """Which of the five check groups a check id belongs to."""
    for prefix, label in _GROUP_PREFIXES:
        if check.startswith(prefix):
            return label
    return "Content"


class CheckResult(NamedTuple):
    report: Report
    doc: Any
    parse_error: Optional[yaml.YAMLError]


def run_checks(text: str) -> CheckResult:
    """Every check, in the order main() has always run them."""
    rep = Report()
    check_raw_text(text, rep)

    doc, parse_error = None, None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        parse_error = e
        mark = getattr(e, "problem_mark", None)
        where = f"line {mark.line + 1}, column {mark.column + 1}" if mark else None
        rep.error("yaml.parse", str(getattr(e, "problem", e)).strip(), where)

    if doc is not None and check_structure(doc, rep):
        check_objects(doc, rep)
        check_references(doc, rep)
        check_content(doc, rep)
    return CheckResult(rep, doc, parse_error)


class PlanStats(NamedTuple):
    counts: Dict[str, int]
    objects: int
    links: int


def _objects(doc: dict, section: str) -> List[dict]:
    items = doc.get(section)
    return [o for o in items if isinstance(o, dict)] if isinstance(items, list) else []


def _count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    return 1 if value else 0


def plan_stats(doc: Any) -> PlanStats:
    """Objects per section and cross-reference links, for the results panel."""
    if not isinstance(doc, dict):
        return PlanStats({k: 0 for k in SECTIONS}, 0, 0)
    counts = {k: len(doc[k]) if isinstance(doc.get(k), list) else 0 for k in SECTIONS}
    links = sum(_count(o.get(field))
                for section, field in (("tactics", "methodologyIds"), ("techniques", "tacticIds"),
                                       ("procedures", "techniqueIds"))
                for o in _objects(doc, section))
    links += sum(1 for o in _objects(doc, "procedures") if o.get("repositoryId"))
    tp = doc.get("testPlan")
    if isinstance(tp, dict):
        links += _count(tp.get("procedureIds"))
    return PlanStats(counts, sum(counts.values()), links)


def read_plan(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# --------------------------------------------------------------------------- repair preview

DUMP_FIXED = ("yaml.anchors", "yaml.bom", "yaml.tabs", "yaml.anchor_name", "yaml.alias_name")
_REPAIR_FIELDS = (("methodologies", ("tags",)), ("tactics", ("methodologyIds", "tags")),
                  ("techniques", ("tacticIds", "tags")), ("procedures", ("techniqueIds", "tags")))


class Change(NamedTuple):
    section: str
    name: str
    field: str
    removed: List[Any]


def copy_for_repair(doc: dict) -> dict:
    """A copy autofix can change without touching `doc`. autofix only reassigns fields,
    so copying each object one level deep is enough."""
    out = dict(doc)
    for section in SECTIONS:
        if isinstance(doc.get(section), list):
            out[section] = [dict(o) if isinstance(o, dict) else o for o in doc[section]]
    if isinstance(doc.get("testPlan"), dict):
        out["testPlan"] = dict(doc["testPlan"])
        if doc.get("runbook") is doc["testPlan"]:
            out["runbook"] = out["testPlan"]
    return out


def can_repair(doc: Any) -> bool:
    """dump() needs a testPlan mapping to anchor the runbook alias on."""
    return isinstance(doc, dict) and isinstance(doc.get("testPlan"), dict)


def repaired_text(doc: dict, text: str) -> Tuple[str, dict]:
    """What --fix would write, without changing `doc`."""
    fixed = copy_for_repair(doc)
    autofix(fixed, text, Report())
    return dump(fixed), fixed


def auto_fixed(doc: Any, rep: Report) -> Set[IssueKey]:
    """The issues in `rep` that a repaired copy would no longer have. Never parses YAML."""
    if not can_repair(doc):
        return set()
    fixed = copy_for_repair(doc)
    autofix(fixed, "", Report())
    fixed["runbook"] = fixed["testPlan"]
    after = Report()
    if check_structure(fixed, after):
        check_objects(fixed, after)
        check_references(fixed, after)
        check_content(fixed, after)
    remaining = {issue_key(i) for i in after.errors + after.warnings}
    gone = set()
    for item in rep.errors + rep.warnings:
        check = item["check"]
        if check in DUMP_FIXED or (not check.startswith("yaml.") and issue_key(item) not in remaining):
            gone.add(issue_key(item))
    return gone


def repair_changes(before: dict, after: dict) -> List[Change]:
    """Per object, the list values the repair removed (for the receipt)."""
    changes = []
    for section, fields in _REPAIR_FIELDS:
        for b, a in zip(_objects(before, section), _objects(after, section)):
            for field in fields:
                old, new = b.get(field), a.get(field)
                if isinstance(old, list) and old != new:
                    kept = new if isinstance(new, list) else []
                    name = str(b.get("shortName") or b.get("name") or "")
                    changes.append(Change(section, name, field, [v for v in old if v not in kept]))
    tb, ta = before.get("testPlan"), after.get("testPlan")
    if isinstance(tb, dict) and isinstance(ta, dict) and isinstance(tb.get("tags"), list) \
            and tb["tags"] != ta.get("tags"):
        changes.append(Change("testPlan", str(tb.get("title") or ""), "tags", list(tb["tags"])))
    return changes


def file_fixes(rep: Report) -> List[str]:
    """File-level fixes a rewrite makes, for the receipt."""
    checks = {i["check"] for i in rep.errors + rep.warnings}
    lines = []
    if "yaml.anchors" in checks:
        lines.append("stray anchors removed")
    if "yaml.bom" in checks:
        lines.append("byte order mark dropped")
    if "yaml.tabs" in checks:
        lines.append("tab characters escaped")
    if any(i["check"] == "schema.sections" and "runbook" in i["message"] for i in rep.errors):
        lines.append("runbook section added")
    elif "runbook.alias" in checks:
        lines.append("runbook made an alias of testPlan")
    return lines


# --------------------------------------------------------------------------- terminal

STOPS = ("#22d3ee", "#818cf8", "#e879f9", "#fb7185")
ACCENT = "#ff5faf"
GREEN = "#4ade80"
RED = "#dc2626"
YELLOW = "#facc15"
CONTENT_WIDTH = 78
MIN_FANCY_COLUMNS = 60
BIG_BANNER_COLUMNS = 74
GLYPH_PROBE = "╭█▀▐❯✔✘─│"


class Caps(NamedTuple):
    fancy: bool
    interactive: bool
    truecolor: bool
    width: int
    height: int


def _isatty(stream: Any) -> bool:
    try:
        return bool(stream is not None and stream.isatty())
    except (AttributeError, ValueError):
        return False


def _can_encode(stream: Any, text: str) -> bool:
    try:
        text.encode(getattr(stream, "encoding", None) or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def detect_mode(plain: bool, json_out: bool, env: Mapping[str, str], stdout: Any, stdin: Any,
                platform: str, size: Tuple[int, int], enable_vt: Callable[[], bool]) -> Caps:
    """Graphics only where they render well and nothing else reads the output."""
    width, height = size
    truecolor = env.get("COLORTERM", "").lower() in ("truecolor", "24bit") or "WT_SESSION" in env
    fancy = (_isatty(stdout) and not plain and not json_out and not env.get("NO_COLOR")
             and env.get("TERM") != "dumb" and _can_encode(stdout, GLYPH_PROBE)
             and width >= MIN_FANCY_COLUMNS)
    if fancy and platform == "win32":
        fancy = ("WT_SESSION" in env or env.get("TERM_PROGRAM") == "vscode") and enable_vt()
    return Caps(bool(fancy), bool(fancy and _isatty(stdin)), truecolor, width, height)


def enable_windows_vt() -> bool:
    """Turn on colour-code processing in a Windows console. False if it can't."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # standard output
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def _rgb(color: str) -> Tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _hex(channels: Any) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(v)))):02x}" for v in channels)


def gradient(stops: Sequence[str], t: float) -> str:
    t = max(0.0, min(1.0, float(t)))
    if len(stops) == 1:
        return stops[0].lower()
    pos = t * (len(stops) - 1)
    i = min(int(pos), len(stops) - 2)
    a, b = _rgb(stops[i]), _rgb(stops[i + 1])
    return _hex(x + (y - x) * (pos - i) for x, y in zip(a, b))


def shade(color: str, k: float) -> str:
    return _hex(v * k for v in _rgb(color))


_CUBE = (0, 95, 135, 175, 215, 255)


@functools.lru_cache(maxsize=None)
def xterm256(color: str) -> int:
    """Nearest xterm-256 colour: the 6x6x6 cube or the 24 greys."""
    r, g, b = _rgb(color)

    def dist(c: Tuple[int, int, int]) -> int:
        return (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2

    idx = [min(range(6), key=lambda i: abs(_CUBE[i] - v)) for v in (r, g, b)]
    best, best_dist = 16 + 36 * idx[0] + 6 * idx[1] + idx[2], dist(tuple(_CUBE[i] for i in idx))
    for i in range(24):
        level = 8 + 10 * i
        d = dist((level, level, level))
        if d < best_dist:
            best, best_dist = 232 + i, d
    return best


_SGR = {"bold": "1", "dim": "2", "italic": "3", "underline": "4", "strike": "9"}


def style_sgr(spec: str, truecolor: bool) -> str:
    """'bold fg:#rrggbb bg:#rrggbb' -> one escape sequence."""
    codes = []
    for token in spec.split():
        if token in _SGR:
            codes.append(_SGR[token])
        elif token.startswith(("fg:", "bg:")):
            base = "38" if token.startswith("fg:") else "48"
            if truecolor:
                r, g, b = _rgb(token[3:])
                codes.append(f"{base};2;{r};{g};{b}")
            else:
                codes.append(f"{base};5;{xterm256(token[3:])}")
    return f"\x1b[{';'.join(codes)}m" if codes else ""


_ZERO_WIDTH = {"​", "‌", "‍", "︎", "️"}


def cell_width(s: str) -> int:
    """Terminal columns a string takes."""
    total = 0
    for ch in s:
        if ch in _ZERO_WIDTH or unicodedata.combining(ch):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def _cut(word: str, width: int) -> Tuple[str, str]:
    """Split `word` after at most `width` columns (at least one character)."""
    used, i = 0, 0
    while i < len(word) and (i == 0 or used + cell_width(word[i]) <= width):
        used += cell_width(word[i])
        i += 1
    return word[:i], word[i:]


def wrap_cells(text: str, width: int) -> List[str]:
    """Greedy word wrap by terminal columns; words wider than `width` are split."""
    width = max(1, width)
    lines: List[str] = []
    current = ""
    for word in text.split():
        while cell_width(word) > width:
            if current:
                lines.append(current)
                current = ""
            head, word = _cut(word, width)
            lines.append(head)
        if not word:
            continue
        if not current:
            current = word
        elif cell_width(current) + 1 + cell_width(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


def run_plain(args: argparse.Namespace, text: str) -> int:
    """The original plain-text and JSON output, unchanged. Returns the exit code."""
    res = run_checks(text)
    rep, doc = res.report, res.doc

    fixes = []
    if args.fix and doc is not None:
        fixes = autofix(doc, text, rep)
        with open(args.fix, "w", encoding="utf-8") as f:
            f.write(dump(doc))

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

    return 1 if rep.errors else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a PlexTrac Runbooks V2 "
                                             "test plan YAML before importing it.")
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--fix", metavar="OUT", help="write a repaired copy to OUT")
    ap.add_argument("--quiet", action="store_true", help="errors only")
    args = ap.parse_args(argv)

    try:
        text = read_plan(args.path)
    except (OSError, UnicodeDecodeError) as e:
        print(f"cannot read {args.path}: {e}", file=sys.stderr)
        return 2
    return run_plain(args, text)


if __name__ == "__main__":
    sys.exit(main())

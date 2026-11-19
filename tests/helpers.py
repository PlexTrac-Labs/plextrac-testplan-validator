"""Shared test helpers: load the script, build sample plans, run the command line."""
import importlib.util
import os
import re
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Union

import yaml

SCRIPT = Path(__file__).resolve().parent.parent / "validate_test_plan.py"
OWASP_DIR = SCRIPT.parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden"

_module = None


def load_script():
    """Import validate_test_plan.py by path, once."""
    global _module
    if _module is None:
        spec = importlib.util.spec_from_file_location("validate_test_plan", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _module = module
    return _module


def _cuid(n: int) -> str:
    return f"c{n:024d}"


def mini_plan() -> dict:
    """A small, valid plan shaped like a real PlexTrac export."""
    counter = iter(range(1, 100))

    def obj(name, short, description, **extra):
        base = {"id": _cuid(next(counter)), "name": name, "shortName": short, "description": description}
        base.update(extra)
        return base

    common = {"origin": "import", "isEditable": True, "sourceId": None, "sourceKey": None, "sourceValue": None}
    meth = obj("Mini Methodology", "MINI-M1", "Mini methodology.", **common, tags=[])
    tactics = [obj(f"Mini Tactic {i}", f"MINI-T{i}", f"Tactic {i}.", **common,
                   methodologyIds=[meth["id"]], tags=[]) for i in (1, 2)]
    techniques = [obj(f"Mini Technique {i}", f"MINI-K{i}", f"Technique {i}.", **common,
                      tacticIds=[tactics[i - 1]["id"]], tags=[]) for i in (1, 2)]
    repo = obj("Mini Repository", "MINI-R1", "Mini repository.", type="managed", origin="import", isEditable=True)
    words = ("one", "two", "three", "four")
    procedures = []
    for i in range(1, 5):
        technique = techniques[0] if i <= 2 else techniques[1]
        p = obj(f"Mini procedure {words[i - 1]}", f"MINI-P{i}", f"Procedure {words[i - 1]}.")
        p.update(repositoryId=repo["id"], **common,
                 executionSteps=[{"description": f"Step for procedure {words[i - 1]}.", "successCriteria": None}],
                 techniqueIds=[technique["id"]], tags=[])
        procedures.append(p)
    test_plan = {"id": _cuid(next(counter)), "title": "Mini plan", "description": None, "type": "custom",
                 "origin": "api", "isEditable": True, "procedureIds": [p["id"] for p in procedures], "tags": []}
    return {"methodologies": [meth], "tactics": tactics, "techniques": techniques, "repositories": [repo],
            "procedures": procedures, "testPlan": test_plan, "runbook": test_plan}


def _dumped(change=None) -> str:
    doc = mini_plan()
    if change:
        change(doc)
    return load_script().dump(doc)


def _broken(doc, methodology=True, tags=True, unlisted=True):
    if methodology:
        doc["tactics"][0]["methodologyIds"].append("c" + "8" * 24)
    if tags:
        doc["procedures"][1]["tags"] = ["web"]
    if unlisted:
        doc["testPlan"]["procedureIds"].remove(doc["procedures"][3]["id"])


def variant_text(name: str) -> str:
    """YAML text of the mini plan, with one named problem planted in it."""
    ok = _dumped()
    if name == "ok":
        return ok
    if name == "broken":
        return _dumped(_broken)
    if name == "syntax":
        return ok.replace("shortName: MINI-T1\n", "shortName: MINI-T1: draft\n", 1)
    if name == "dangling_methodology":
        return _dumped(lambda d: _broken(d, tags=False, unlisted=False))
    if name == "tags_nonempty":
        return _dumped(lambda d: _broken(d, methodology=False, unlisted=False))
    if name == "tags_null":
        return _dumped(lambda d: d["procedures"][0].update(tags=None))
    if name == "tags_missing":
        return _dumped(lambda d: d["procedures"][0].pop("tags"))
    if name == "dangling_repository":
        return _dumped(lambda d: d["procedures"][0].update(repositoryId="c" + "9" * 24))
    if name == "extra_anchor":
        return re.sub(r"^(\s*)- id:", r"\1- &m1\n\1  id:", ok, count=1, flags=re.M)
    if name == "bom":
        return "﻿" + ok
    if name == "runbook_copy":
        copy = yaml.safe_dump({"runbook": mini_plan()["testPlan"]}, sort_keys=False)
        return ok.replace("runbook: *ref_0\n", copy)
    if name == "runbook_missing":
        return ok.replace("runbook: *ref_0\n", "")
    if name == "tab_in_value":
        return re.sub(r"^(\s*)description: Procedure one\.$", "\\1description: \"a\tb\"", ok, count=1, flags=re.M)
    raise KeyError(name)


class CliRun(NamedTuple):
    stdout: str
    stderr: str
    code: int
    after: Optional[str]


def run_cli(args: List[str], files: Dict[str, Union[str, bytes]], read_after: Optional[str] = None) -> CliRun:
    """Run the script in a fresh temp folder holding `files`, with output piped."""
    with tempfile.TemporaryDirectory() as folder:
        for name, content in files.items():
            path = Path(folder) / name
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=folder, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        after = None
        if read_after and (Path(folder) / read_after).exists():
            after = (Path(folder) / read_after).read_text(encoding="utf-8")
        return CliRun(proc.stdout, proc.stderr, proc.returncode, after)


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class PtySession:
    """The script in a pseudo-terminal, driven like a person at a keyboard (POSIX only)."""

    def __init__(self, args: List[str], cwd: Path, cols: int = 100, rows: int = 40):
        import fcntl
        import pty
        import struct
        import termios
        env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor", PYTHONIOENCODING="utf-8")
        for name in ("NO_COLOR", "COLUMNS", "LINES"):
            env.pop(name, None)
        pid, fd = pty.fork()
        if pid == 0:
            try:
                import signal
                signal.signal(signal.SIGINT, signal.SIG_DFL)  # so Ctrl+C reaches the script
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                os.chdir(str(cwd))
                os.execve(sys.executable, [sys.executable, str(SCRIPT), *args], env)
            finally:
                os._exit(127)
        self.pid, self.fd, self._buf, self.raw = pid, fd, b"", ""

    def _read(self, timeout: float) -> Optional[bool]:
        """True if data arrived, False on timeout, None at end of output."""
        if not select.select([self.fd], [], [], max(0.0, timeout))[0]:
            return False
        try:
            data = os.read(self.fd, 4096)
        except OSError:
            return None
        if not data:
            return None
        self._buf += data
        self.raw = self._buf.decode("utf-8", "replace")
        return True

    def expect(self, text: str, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while text not in _ANSI.sub("", self.raw):
            if time.monotonic() >= deadline or self._read(deadline - time.monotonic()) is None:
                raise AssertionError(f"never saw {text!r}; screen ended with:\n{_ANSI.sub('', self.raw)[-1500:]}")

    def send(self, s: str) -> None:
        os.write(self.fd, s.encode("utf-8"))

    def wait(self, timeout: float = 15) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and self._read(0.2) is not None:
            pass
        _, status = os.waitpid(self.pid, 0)
        os.close(self.fd)
        return os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1


def format_run(run: CliRun) -> str:
    return f"== exit ==\n{run.code}\n== stdout ==\n{run.stdout}== stderr ==\n{run.stderr}"


class Case(NamedTuple):
    name: str
    args: List[str]
    files: Dict[str, Union[str, bytes]]
    read_after: Optional[str]


def golden_cases() -> List[Case]:
    broken = variant_text("broken")
    cases = [
        Case("mini_ok", ["mini_ok.yaml"], {"mini_ok.yaml": variant_text("ok")}, None),
        Case("broken", ["broken.yaml"], {"broken.yaml": broken}, None),
        Case("broken_quiet", ["broken.yaml", "--quiet"], {"broken.yaml": broken}, None),
        Case("broken_json", ["broken.yaml", "--json"], {"broken.yaml": broken}, None),
        Case("broken_fix", ["broken.yaml", "--fix", "fixed.yaml"], {"broken.yaml": broken}, "fixed.yaml"),
        Case("syntax", ["syntax.yaml"], {"syntax.yaml": variant_text("syntax")}, None),
        Case("missing", ["nope.yaml"], {}, None),
    ]
    for name in ("OWASP_WSTG.yaml", "OWASP_MASTG.yaml"):
        path = OWASP_DIR / name
        if path.exists():
            cases.append(Case("owasp_" + name[6:-5].lower(), [name], {name: path.read_bytes()}, None))
    return cases

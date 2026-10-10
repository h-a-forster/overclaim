"""Verification evidence: which commands ran tests, how they ended, and what came after edits.

Shell parsing here is deliberately small: split a command line into simple commands on
``&&``, ``||``, ``|``, ``;``, ``&`` and newlines (quotes respected), skip runner prefixes
(``uv run``, ``python -m``, ``npx``, ``timeout 60``, ``VAR=1``), then look at the program in
command position. ``cat pytest.ini`` or ``pip install pytest`` are therefore not test runs.
"""

from __future__ import annotations

import fnmatch
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass

from overclaim.models import Command, Edit, Evidence, Transcript, Verification

# --- splitting command lines --------------------------------------------------------------

_PUNCT = frozenset("|&;()<>")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)(?:\n\s*\2\s*(?=\n|$)|\Z)", re.S)
_NULL_TARGETS = frozenset({"/dev/null", "nul", "$null", "/dev/stdout", "/dev/stderr"})
_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")


@dataclass(frozen=True, slots=True)
class _Simple:
    """One simple command: its words, files it redirects output to, and the separator after."""

    words: tuple[str, ...]
    writes: tuple[str, ...]
    sep: str  # "&&", "||", "|", ";", "&" or "" at the end


def _segments(command: str, depth: int = 0) -> list[_Simple]:
    """The simple commands of a command line, in order.

    The script of a shell wrapper (``bash -c '...'``, ``pwsh -Command ...``, ``cmd /c ...``)
    is split in place of the wrapper, so ``bash -lc 'pytest | tail'`` is a pipe.
    """
    text = command.replace("\\\r\n", " ").replace("\\\n", " ").replace("\r\n", "\n")
    text = _HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0] + "\n", text)
    tokens = _tokens(text.replace("\n", " ; "))
    out: list[_Simple] = []
    words: list[str] = []
    writes: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok and set(tok) <= _PUNCT:
            if ">" in tok or "<" in tok:
                target = tokens[i + 1] if i + 1 < len(tokens) else ""
                if words and words[-1].isdigit():
                    words.pop()  # the fd of `2>&1`
                if ">" in tok and not tok.endswith("&") and target.lower() not in _NULL_TARGETS:
                    writes.append(target)
                i += 2
                continue
            sep = next((s for s in ("||", "&&", "|", ";", "&") if s in tok), "")
            if sep and (words or writes):
                out.append(_Simple(tuple(words), tuple(writes), sep))
                words, writes = [], []
            i += 1
            continue
        if tok.startswith("#"):  # a comment runs to the end of the line, now a ";"
            while i < len(tokens) and ";" not in tokens[i]:
                i += 1
            continue
        words.append(tok)
        i += 1
    if words or writes:
        out.append(_Simple(tuple(words), tuple(writes), ""))
    if depth >= 3:
        return out
    expanded: list[_Simple] = []
    for seg in out:
        inner = _wrapped_script(seg.words)
        sub = _segments(inner, depth + 1) if inner else []
        if not sub:
            expanded.append(seg)
            continue
        last = sub[-1]
        expanded += [*sub[:-1], _Simple(last.words, last.writes + seg.writes, seg.sep)]
    return expanded


_POSIX_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "ash"})


def _wrapped_script(words: Sequence[str]) -> str | None:
    """The script run by a shell wrapper, or None when ``words`` is not one."""
    w = [x for x in words if not _ASSIGNMENT.match(x)] if words else []
    if not w:
        return None
    prog = _program(w[0])
    for j in range(1, len(w)):
        a = w[j]
        if prog in _POSIX_SHELLS:
            if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", a):
                return w[j + 1] if j + 1 < len(w) else None
            if not a.startswith(("-", "+")):
                return None  # `bash script.sh`
        elif prog in ("pwsh", "powershell"):
            if a.lower() in ("-c", "-command"):
                return " ".join(w[j + 1 :]) or None
        elif prog == "cmd":
            if a.lower() in ("/c", "/k"):
                return " ".join(w[j + 1 :]) or None
        else:
            return None
    return None


def _tokens(text: str) -> list[str]:
    try:
        lex = shlex.shlex(text, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        lex.escape = ""  # keep Windows paths (.venv\Scripts\pytest.exe) and PowerShell intact
        return list(lex)
    except ValueError:  # unbalanced quotes: fall back to a crude split
        return re.findall(r"&&|\|\||[|&;()<>]+|[^\s|&;()<>]+", text)


def _program(word: str) -> str:
    name = re.split(r"[\\/]", word)[-1].lower()
    return re.sub(r"\.(?:exe|cmd|bat)$", "", name)


_PREFIX_1 = frozenset(
    {"env", "time", "nice", "nohup", "sudo", "doas", "command", "exec", "xvfb-run", "stdbuf"}
    | {"npx", "bunx", "pnpx", "uvx", "caffeinate", "chronic"}
)
_PREFIX_2 = frozenset(
    {
        ("uv", "run"),
        ("poetry", "run"),
        ("pdm", "run"),
        ("hatch", "run"),
        ("rye", "run"),
        ("pipenv", "run"),
        ("conda", "run"),
        ("pixi", "run"),
        ("pnpm", "exec"),
        ("pnpm", "dlx"),
        ("yarn", "exec"),
        ("yarn", "dlx"),
        ("npm", "exec"),
        ("bundle", "exec"),
    }
)
# Options of the prefixes above that take a separate value: `uv run --project DIR pytest`.
_VALUE_OPTIONS = frozenset(
    {"--project", "--directory", "--python", "-p", "--package", "--env-file", "--extra"}
    | {"--group", "--with", "--index", "-n", "--name", "--prefix", "-u", "--user", "-C"}
    | {"-s", "--signal", "-k", "--kill-after", "--cwd", "--dir", "--filter", "-e", "--env"}
)
_PYTHON = re.compile(r"^(?:python[\d.]*|py|pypy[\d.]*)$")
_COVERAGE_VALUE_OPTIONS = frozenset(
    {"--rcfile", "--source", "--include", "--omit", "--context", "--data-file", "--concurrency"}
)


def _command_words(words: Sequence[str]) -> list[str]:
    """``words`` from the program that does the work: runner prefixes and env removed."""
    w = list(words)
    for _ in range(8):  # prefixes nest (`timeout 60 uv run pytest`); bounded for safety
        while w and _ASSIGNMENT.match(w[0]):
            w = w[1:]
        if not w:
            return w
        prog = _program(w[0])
        if len(w) > 1 and (prog, w[1]) in _PREFIX_2:
            w = _skip_options(w[2:])
        elif prog == "timeout":
            w = _skip_options(w[1:])[1:]  # then the duration
        elif prog in _PREFIX_1:
            w = _skip_options(w[1:])
        elif prog == "coverage" and len(w) > 1 and w[1] == "run":
            j = 2  # `coverage run [options] -m pytest` or `coverage run [options] script.py`
            while j < len(w) and w[j].startswith("-") and w[j] != "-m":
                j += 2 if w[j] in _COVERAGE_VALUE_OPTIONS else 1
            return w[j + 1 :] if j < len(w) and w[j] == "-m" else w[j:]
        elif _PYTHON.match(prog):
            j = 1
            while j < len(w) and w[j].startswith("-") and w[j] not in ("-m", "-c"):
                j += 2 if w[j] in ("-X", "-W") else 1
            if j < len(w) and w[j] == "-m" and j + 1 < len(w):
                w = w[j + 1 :]  # the module may itself be a runner: `python -m coverage run`
                continue
            if j < len(w) and w[j].lower().endswith(".py"):
                return w[j:]
            return w
        else:
            return w
    return w


def _skip_options(w: list[str]) -> list[str]:
    i = 0
    while i < len(w) and (w[i].startswith("-") or _ASSIGNMENT.match(w[i])):
        i += 2 if w[i] in _VALUE_OPTIONS else 1
    return w[i:]


# --- test commands -----------------------------------------------------------------------

_NOT_A_RUN = frozenset({"--version", "-V", "--help", "-h", "--collect-only", "--co", "--list"})
_TEST_TOOLS = frozenset(
    {"pytest", "py.test", "unittest", "nose2", "ward", "tox", "nox", "jest", "vitest", "mocha"}
    | {"rspec", "phpunit", "pest", "ctest", "ava", "karma", "behave", "trial", "invoke-pester"}
)
_SUBCOMMAND_TESTS = {
    "go": {"test"},
    "cargo": {"test", "nextest"},
    "dotnet": {"test"},
    "deno": {"test"},
    "bun": {"test"},
    "mix": {"test"},
    "swift": {"test"},
    "rake": {"test", "spec"},
    "rails": {"test"},
    "make": {"test", "check"},
    "just": {"test"},
    "manage.py": {"test"},
    "playwright": {"test"},
    "hatch": {"test"},
}
_SCRIPT_RUNNERS = frozenset({"npm", "pnpm", "yarn", "bun"})
_TEST_SCRIPT = re.compile(r"^(?:test|t|tests|spec|test[:_-][\w:-]+)$")
_RUNNER_SCRIPT = re.compile(r"^(?:run[-_]?)?tests?(?:[-_]\w+)?\.(?:sh|ps1|bat|cmd)$")
_ABSOLUTE = re.compile(r"^(?:/|~|[A-Za-z]:|\$|%)")
_TEST_DIRS = frozenset({"test", "tests", "testing", "spec", "specs", "__tests__"})


def _is_test_script(word: str) -> bool:
    """A script run directly that is a project test runner or test module.

    Project runner scripts (``./run_tests.sh``, ``scripts/test.ps1``) and Python files in a
    tests directory (``python tests/test_api.py``) count, by relative path. Ad-hoc scripts
    (``python test_repro.py``, ``python /tmp/test_x.py``) do not: they are not the suite.
    """
    path = word.replace("\\", "/")
    if _ABSOLUTE.match(path):
        return False
    parts = [x for x in path.lower().split("/") if x not in ("", ".")]
    if not parts:
        return False
    if _RUNNER_SCRIPT.match(parts[-1]):
        return True
    return parts[-1].endswith(".py") and any(d in _TEST_DIRS for d in parts[:-1])


def _is_test_words(words: Sequence[str]) -> bool:
    w = _command_words(words)
    if not w:
        return False
    prog, args = _program(w[0]), w[1:]
    info = _NOT_A_RUN - {"-V"} if prog == "ctest" else _NOT_A_RUN  # ctest -V is verbose
    if info.intersection(args):
        return False
    if prog in _TEST_TOOLS or _is_test_script(w[0]):
        return True
    first = args[0] if args else ""
    if prog in _SCRIPT_RUNNERS:
        if first == "run" and len(args) > 1:
            first = args[1]
        return bool(_TEST_SCRIPT.match(first)) or first in _TEST_TOOLS
    if prog in ("mvn", "mvnw"):
        return any(a in ("test", "verify") for a in args)
    if prog in ("gradle", "gradlew"):
        return any(a in ("test", "check") or a.endswith(":test") for a in args)
    return first in _SUBCOMMAND_TESTS.get(prog, ())


def _test_segment(seg: _Simple, extra: Sequence[re.Pattern[str]]) -> bool:
    return _is_test_words(seg.words) or any(p.search(" ".join(seg.words)) for p in extra)


def is_test_command(cmd: str, extra: Sequence[re.Pattern[str]] = ()) -> bool:
    """True when some simple command in ``cmd`` runs a test suite.

    ``extra`` patterns are searched in each simple command (for project-specific runners).
    """
    return any(_test_segment(seg, extra) for seg in _segments(cmd))


# --- outcomes ----------------------------------------------------------------------------

_M = re.MULTILINE
_FAILED = (
    re.compile(r"^[=\s]*(?:.*\b)?[1-9]\d* (?:failed|errors?)\b.*\bin [\d.]+m?s\b", _M),  # pytest
    re.compile(r"^FAILED \((?:failures|errors)=\d+", _M),  # unittest
    re.compile(r"^\s*Tests?:?\s+.*\b[1-9]\d* failed\b", _M),  # jest, vitest
    re.compile(r"^(?:FAIL|--- FAIL:)(?:\s|$)", _M),  # go test
    re.compile(r"test result: FAILED\b"),  # cargo
    re.compile(r"^\s*[1-9]\d* failing\b", _M),  # mocha
    re.compile(r"\b\d+ examples?, [1-9]\d* failures?\b"),  # rspec
    re.compile(r"^(?:FAILURES|ERRORS)!\s*$", _M),  # phpunit
    re.compile(r"^\s*Failed!\s+-\s+Failed:\s+[1-9]", _M),  # dotnet test
    re.compile(r"\btests passed, [1-9]\d* tests? failed out of\b"),  # ctest
    re.compile(r"^\s*ERROR:\s+\S+: commands failed", _M),  # tox
    re.compile(r"^nox > Session \S+ failed", _M),  # nox
)
_PASSED = (
    re.compile(r"^[=\s]*(?:.*\b)?[1-9]\d* passed\b.*\bin [\d.]+m?s\b", _M),  # pytest
    re.compile(r"^Ran [1-9]\d* tests? in [\d.]+s\s*\n(?:\s*\n)*\s*OK\b", _M),  # unittest
    re.compile(r"^\s*Tests?:?\s+.*\b[1-9]\d* passed\b", _M),  # jest, vitest
    re.compile(r"^ok\s+\S+\s+(?:[\d.]+s|\(cached\))", _M),  # go test
    re.compile(r"test result: ok\. [1-9]"),  # cargo
    re.compile(r"^\s*[1-9]\d* passing\b", _M),  # mocha
    re.compile(r"\b[1-9]\d* examples?, 0 failures\b"),  # rspec
    re.compile(r"^OK \([1-9]\d* tests?", _M),  # phpunit
    re.compile(r"^\s*Passed!\s+-\s+Failed:\s+0\b", _M),  # dotnet test
    re.compile(r"\b100% tests passed\b"),  # ctest
    re.compile(r"^\s*congratulations :\)", _M),  # tox
    re.compile(r"^nox > Session \S+ was successful", _M),  # nox
)
_NO_TESTS = re.compile(
    r"\bno tests ran\b|^collected 0 items\b|\bNO TESTS RAN\b|^Ran 0 tests\b|\bNo tests found\b"
    r"|\bno test files\b|\bwarning: no tests to run\b|^running 0 tests\b",
    _M,
)


def output_verdict(output: str) -> bool | None:
    """True/False when test output shows a pass/fail summary, else None. Failures win."""
    text = output.replace("\r\n", "\n")
    if any(rx.search(text) for rx in _FAILED):
        return False
    if any(rx.search(text) for rx in _PASSED):
        return True
    return None


def _exit_is_own(segs: Sequence[_Simple], k: int, command: str) -> bool:
    """Whether the command line's exit status is that of simple command ``k``.

    True when only ``&&`` follows it (``|`` too under ``pipefail``): ``pytest | tail`` and
    ``pytest; echo done`` exit with the status of the last program, ``a || pytest`` may not
    run pytest at all.
    """
    if k > 0 and segs[k - 1].sep == "||":
        return False
    ok = {"&&", "|"} if "pipefail" in command else {"&&"}
    return all(s.sep in ok for s in segs[k:-1]) and segs[-1].sep in ("", ";")


def test_outcome(cmd: Command, extra: Sequence[re.Pattern[str]] = ()) -> bool | None:
    """True passed, False failed, None unknown, for a test command.

    The exit code decides when it belongs to the test tool itself; otherwise (a pipe, a
    trailing command, no exit code in the transcript) the output summary does. Output that
    shows failures overrides exit 0; a run that collected no tests is unknown.
    """
    segs = _segments(cmd.text)
    hits = [i for i, s in enumerate(segs) if _test_segment(s, extra)]
    verdict = output_verdict(cmd.output)
    no_tests = bool(_NO_TESTS.search(cmd.output))
    if hits and cmd.exit_code is not None and _exit_is_own(segs, hits[-1], cmd.text):
        if cmd.exit_code != 0:
            return None if no_tests and verdict is None else False
        if verdict is False:
            return False
        return None if no_tests else True
    if verdict is None or (verdict is True and no_tests):
        return None
    return verdict


test_outcome.__test__ = False  # type: ignore[attr-defined]  # not a pytest test


# --- edits -------------------------------------------------------------------------------

_PS_WRITERS = frozenset({"set-content", "add-content", "out-file", "new-item"})
_PS_PATH = re.compile(r"^-(?:path|filepath|literalpath)$", re.IGNORECASE)


def shell_writes(command: str) -> list[str]:
    """Files a shell command obviously writes ("?" when the target is unclear).

    Conservative: output redirection to a file, ``tee``, ``sed -i`` / ``perl -i``, and the
    PowerShell cmdlets ``Set-Content``, ``Add-Content``, ``Out-File``, ``New-Item``. Files
    written by programs (``python -c``, scripts, formatters) are not seen.
    """
    out: list[str] = []
    for seg in _segments(command):
        out.extend(t for t in seg.writes if t)
        w = _command_words(seg.words)
        if not w:
            continue
        prog, args = _program(w[0]), w[1:]
        if prog == "tee":
            out.extend(a for a in args if not a.startswith("-"))
        elif prog in ("sed", "perl") and any(
            re.match(r"^-[a-zA-Z]*i", a) or a.startswith("--in-place") for a in args
        ):
            files: list[str] = []
            scripted = skip = False
            for a in args:
                if skip:
                    skip = False
                elif a in ("-e", "-f", "--expression", "--file") or re.match(r"^-\w*e$", a):
                    scripted = skip = True  # the script is the next word, not a file
                elif not a.startswith("-"):
                    files.append(a)
            out.extend((files if scripted else files[1:]) or ["?"])
        elif prog in _PS_WRITERS:
            named = [args[i + 1] for i, a in enumerate(args[:-1]) if _PS_PATH.match(a)]
            positional = [a for a in args if not a.startswith("-")]
            out.append((named or positional or ["?"])[0])
    return out


DOC_GLOBS: tuple[str, ...] = (
    "*.md",
    "*.markdown",
    "*.rst",
    "*.txt",
    "*.adoc",
    "CHANGELOG*",
    "LICENSE*",
    "docs/**",
)
"""Files whose edits do not need a test run: documentation, changelogs, licences."""


def path_matches(path: str, globs: Sequence[str]) -> bool:
    """True when ``path`` matches a glob, case-insensitively, on its posix form.

    A glob without ``/`` matches the file name; one with ``/`` matches the path or any
    trailing part of it, so ``docs/**`` matches ``docs/a.py`` and ``C:\\repo\\docs\\a.py``.
    """
    norm = path.replace("\\", "/").lower()
    parts = [p for p in norm.split("/") if p]
    if not parts:
        return False
    for glob in globs:
        g = glob.replace("\\", "/").lower()
        if "/" not in g:
            if fnmatch.fnmatchcase(parts[-1], g):
                return True
        elif any(fnmatch.fnmatchcase("/".join(parts[i:]), g) for i in range(len(parts))):
            return True
    return False


SOURCE_EXTENSIONS = frozenset(
    {
        "py",
        "pyi",
        "pyx",
        "js",
        "jsx",
        "mjs",
        "cjs",
        "ts",
        "tsx",
        "mts",
        "cts",
        "vue",
        "svelte",
        "astro",
        "go",
        "rs",
        "java",
        "kt",
        "kts",
        "scala",
        "groovy",
        "gradle",
        "c",
        "h",
        "cc",
        "cpp",
        "cxx",
        "hpp",
        "hh",
        "m",
        "mm",
        "cs",
        "fs",
        "vb",
        "swift",
        "dart",
        "rb",
        "php",
        "pl",
        "pm",
        "lua",
        "r",
        "jl",
        "ex",
        "exs",
        "erl",
        "hs",
        "clj",
        "sh",
        "bash",
        "zsh",
        "ps1",
        "psm1",
        "bat",
        "cmd",
        "sql",
        "html",
        "htm",
        "css",
        "scss",
        "sass",
        "less",
        "proto",
        "graphql",
        "tf",
        "cmake",
        "mk",
        "toml",
        "yaml",
        "yml",
        "ini",
        "cfg",
        "conf",
    }
)
"""Extensions of files whose shell writes count as edits (code and build configuration)."""

_TEMP_DIR = re.compile(
    r"^(?:/tmp/|/var/tmp/|/private/tmp/|/dev/|~/appdata/local/temp/|[a-z]:/windows/temp/"
    r"|(?:[a-z]:|/[a-z])/(?:[^/]+/)*appdata/local/temp/|[a-z]:/temp/|[a-z]:/tmp/)",
    re.IGNORECASE,
)


def _source_like(target: str) -> bool:
    """Whether a shell write target looks like a project source file.

    Counted: paths with a code or build-config extension (``SOURCE_EXTENSIONS``) outside temp
    directories, files without an extension given by relative path (``Makefile``), and writes
    whose target is unknown (``?``). Not counted: logs, data and scratch output (``> out.txt``,
    ``> result.json``, ``> /tmp/x.py``) and targets in variables (``$TMPDIR/x``, ``%TEMP%``).
    """
    if target == "?":
        return True
    path = target.strip("'\"").replace("\\", "/")
    if not path or path.startswith(("$", "%")) or _TEMP_DIR.match(path):
        return False
    name = path.rstrip("/").rsplit("/", 1)[-1]
    if not name or name in (".", ".."):
        return False
    stem, dot, ext = name.lstrip(".").rpartition(".")
    if dot and stem:
        return ext.lower() in SOURCE_EXTENSIONS
    return not _ABSOLUTE.match(path)


def _counted_edits(t: Transcript, include_shell: bool, ignore: Sequence[str]) -> list[Edit]:
    edits = [e for e in t.edits if not path_matches(e.path, ignore)]
    if include_shell:
        for c in t.commands:
            targets = [
                p
                for p in shell_writes(c.text)
                if _source_like(p) and (p == "?" or not path_matches(p, ignore))
            ]
            if targets:
                edits.append(Edit(c.index, targets[0], "shell"))
    return sorted(edits, key=lambda e: e.index)


def assess(
    t: Transcript,
    extra_test_patterns: Sequence[re.Pattern[str]] = (),
    shell_writes: bool = True,
    ignore_edits: Sequence[str] = DOC_GLOBS,
) -> Evidence:
    """Verification evidence for a transcript: test runs, the last edit, and the verdict.

    The verdict judges the last test run after the last counted edit. Without counted edits
    it judges the last test run of the session (``test_runs_after_last_edit`` is then every
    run), and is ``NO_EDITS`` only when there are neither counted edits nor test runs.

    Edits to files matching ``ignore_edits`` (documentation by default; pass ``()`` to count
    every edit) are not counted, and ``last_edit`` is the last counted edit. With
    ``shell_writes`` a command that writes a source-like file (see ``_source_like``) counts
    as an edit; a test command that is itself such a write counts as after it.
    """
    edits = _counted_edits(t, shell_writes, ignore_edits)
    runs = tuple(c for c in t.commands if is_test_command(c.text, extra_test_patterns))
    last = edits[-1] if edits else None
    if last is None and not runs:
        return Evidence(Verification.NO_EDITS, None, runs, runs)
    after = runs if last is None else tuple(c for c in runs if c.index >= last.index)
    if not after:
        verification = Verification.NOT_RUN
    else:
        outcome = test_outcome(after[-1], extra_test_patterns)
        verification = {
            True: Verification.PASSED,
            False: Verification.FAILED,
            None: Verification.UNKNOWN,
        }[outcome]
    return Evidence(verification, last, runs, after)

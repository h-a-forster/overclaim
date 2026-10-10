from __future__ import annotations

import re
from pathlib import Path

import pytest

from overclaim import evidence
from overclaim.models import Command, Edit, Transcript, Verification
from overclaim.transcript import load

FIX = Path(__file__).parent / "fixtures" / "transcripts"


def cmd(text: str, exit_code: int | None = 0, output: str = "", index: int = 0) -> Command:
    is_error = None if exit_code is None else exit_code != 0
    return Command(index, text, exit_code, is_error, output)


@pytest.mark.parametrize(
    "text",
    [
        "pytest",
        "pytest -q tests/test_x.py",
        "py.test",
        "python -m pytest -x",
        "python3.12 -X utf8 -m unittest discover -s tests",
        "python -m unittest",
        "uv run pytest",
        "uv run --project pkg pytest -q",
        "poetry run pytest",
        "cd sub && pytest",
        "FOO=1 BAR=2 pytest",
        "env PYTHONPATH=src pytest",
        "timeout 60 pytest",
        "timeout -s KILL 60 uv run pytest",
        "pytest 2>&1 | tail -n 20",
        ".venv\\Scripts\\pytest.exe -q",
        "C:/Python312/python.exe -m pytest",
        "tox -e py312",
        "nox",
        "npm test",
        "npm run test:unit",
        "pnpm test",
        "yarn test",
        "npx jest --ci",
        "npx vitest run",
        "go test ./...",
        "cargo test --all",
        "cargo nextest run",
        "mvn -q test",
        "./gradlew test",
        "make test",
        "ctest --output-on-failure",
        "dotnet test",
        "bundle exec rspec",
        "vendor/bin/phpunit",
        "mocha",
        "python manage.py test",
        "python tests/test_calc.py",
        "coverage run -m pytest",
        "python -m coverage run --branch -m pytest -q",
        "uv run coverage run --source src -m pytest",
        "bash -c 'pytest -q'",
        "bash -lc 'cd sub && npm test'",
        'sh -c "go test ./..."',
        "pwsh -NoProfile -Command Invoke-Pester",
        "cmd /c npm test",
        "npx playwright test",
        "hatch test",
        "ctest -V",
        "./scripts/run_tests.sh",
        "set -o pipefail; pytest | tee log.txt",
    ],
)
def test_is_test_command(text: str) -> None:
    assert evidence.is_test_command(text)


@pytest.mark.parametrize(
    "text",
    [
        "cat pytest.ini",
        "pip install pytest",
        "uv add --dev pytest",
        "pytest --version",
        "python -m pytest --collect-only",
        "grep -r pytest .",
        "ls tests",
        "git commit -m 'make pytest pass'",
        "echo 'run pytest later'",
        "test -f setup.py",
        "npm install",
        "go build ./...",
        "python -c 'import pytest'",
        "cat <<'EOF' > notes.md\npytest -q\nEOF",
        "python test_calc.py",
        "python /tmp/test_repro.py",
        "python C:/Users/me/AppData/Local/Temp/test_x.py",
        "python scripts/test_helper.py",
        "bash -c 'cat pytest.ini'",
        "bash scripts/setup.sh",
        "coverage report",
        "pytest -V",
        "",
    ],
)
def test_is_not_test_command(text: str) -> None:
    assert not evidence.is_test_command(text)


def test_extra_patterns() -> None:
    extra = (re.compile(r"\bcheck\.sh\b"),)
    assert not evidence.is_test_command("./check.sh --fast")
    assert evidence.is_test_command("./check.sh --fast", extra)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (cmd("pytest", 0), True),
        (cmd("pytest", 1), False),
        (cmd("cd x && pytest -q", 2, "1 failed in 0.1s"), False),
        (cmd("pytest", 0, "== 1 failed, 3 passed in 0.12s =="), False),  # output beats exit 0
        (cmd("pytest", 0, "0 failed, 3 passed in 0.12s"), True),
        (cmd("pytest", 5, "no tests ran in 0.01s"), None),
        (cmd("pytest", 0, "collected 0 items\n\nno tests ran in 0.01s"), None),
        (cmd("pytest | tail -5", 0, "3 passed in 0.5s"), True),
        (cmd("pytest | tail -5", 0, "1 failed, 2 passed in 0.5s"), False),
        (cmd("pytest | tail -5", 0, "nothing useful"), None),
        (cmd("pytest; echo done", 0, "done"), None),
        (cmd("pytest || true", 0, ""), None),
        (cmd("false || pytest", 0, ""), None),
        (cmd("pytest &", 0, ""), None),
        (cmd("set -o pipefail; pytest | tee log", 1, ""), False),
        (cmd("pytest", None, "3 passed in 0.5s"), True),
        (cmd("pytest", None, ""), None),
        (cmd("python -m unittest", None, "Ran 2 tests in 0.002s\n\nOK"), True),
        (
            cmd("python -m unittest", None, "Ran 2 tests in 0.002s\r\n\r\nFAILED (failures=1)"),
            False,
        ),
        (cmd("python -m unittest", None, "Ran 0 tests in 0.000s\n\nNO TESTS RAN"), None),
        (cmd("go test ./... | cat", 0, "ok  \texample.com/x\t0.01s"), True),
        (cmd("go test ./... | cat", 0, "--- FAIL: TestX (0.00s)\nFAIL\texample.com/x"), False),
        (cmd("cargo test | tail", 0, "test result: ok. 4 passed; 0 failed"), True),
        (cmd("cargo test | tail", 0, "test result: FAILED. 3 passed; 1 failed"), False),
        (cmd("npx jest | tail", 0, "Tests:       1 failed, 4 passed, 5 total"), False),
        (cmd("npx vitest run | tail", 0, " Tests  5 passed (5)"), True),
        (cmd("npx mocha | tail", 0, "  4 passing (12ms)\n  1 failing"), False),
        (cmd("rspec | tail", 0, "10 examples, 0 failures"), True),
        (cmd("dotnet test | tail", 0, "Passed!  - Failed:     0, Passed:    12"), True),
    ],
)
def test_test_outcome(command: Command, expected: bool | None) -> None:
    assert evidence.test_outcome(command) is expected


def test_output_verdict() -> None:
    assert evidence.output_verdict("") is None
    assert evidence.output_verdict("== 3 passed in 1.2s ==") is True
    assert evidence.output_verdict("== 3 passed, 1 error in 1.2s ==") is False
    assert evidence.output_verdict("FAILED (errors=1)") is False
    assert evidence.output_verdict("ERROR:root:logged while passing\nRan 1 test in 0.1s\n\nOK")


@pytest.mark.parametrize(
    ("command", "writes"),
    [
        ("echo x > a.txt", ["a.txt"]),
        ("echo x >> logs/a.txt", ["logs/a.txt"]),
        ("pytest > /dev/null 2>&1", []),
        ("pytest 2>&1 | tee out.log", ["out.log"]),
        ("sed -i 's/a/b/' src/x.py", ["src/x.py"]),
        ("sed -i -e 's/a/b/' x.py y.py", ["x.py", "y.py"]),
        ("perl -pi -e 's/a/b/' x.pl", ["x.pl"]),
        ("cat <<'EOF' > f.py\nprint('x > y')\nEOF", ["f.py"]),
        ("Set-Content -Path a.txt -Value 'x'", ["a.txt"]),
        ("'x' | Out-File notes.md", ["notes.md"]),
        ("python -c \"open('a','w').write('x')\"", []),
        ("grep 'a > b' file.txt", []),
        ("git diff", []),
        ("sed --in-place 's/a/b/' x.py", ["x.py"]),
        ("sed --in-place=.bak -e 's/a/b/' x.py", ["x.py"]),
        ("bash -c 'echo x > gen.py'", ["gen.py"]),
    ],
)
def test_shell_writes(command: str, writes: list[str]) -> None:
    assert evidence.shell_writes(command) == writes


@pytest.mark.parametrize(
    ("run", "verification"),
    [
        ("pass", Verification.PASSED),
        ("pipe", Verification.PASSED),
        ("editafter", Verification.NOT_RUN),
        ("fail", Verification.FAILED),  # no edits: the last test run is judged
        ("bash", Verification.FAILED),
    ],
)
@pytest.mark.parametrize("kind", ["stream", "session"])
def test_assess_real_transcripts(run: str, kind: str, verification: Verification) -> None:
    ev = evidence.assess(load(FIX / f"claude-{kind}-{run}.jsonl"))
    assert ev.verification is verification


def test_assess_real_runs_in_detail() -> None:
    ev = evidence.assess(load(FIX / "claude-stream-pipe.jsonl"))
    assert [evidence.test_outcome(c) for c in ev.test_runs] == [False, False, True]
    assert len(ev.test_runs_after_last_edit) == 1
    assert ev.last_edit is not None and ev.last_edit.path.endswith("calc.py")
    editafter = evidence.assess(load(FIX / "claude-session-editafter.jsonl"))
    # The later Write of NOTES.md is documentation: the code edit before it is the last edit.
    assert editafter.last_edit is not None and editafter.last_edit.tool == "Edit"
    assert editafter.last_edit.path.endswith("calc.py")
    every = evidence.assess(load(FIX / "claude-session-editafter.jsonl"), ignore_edits=())
    assert every.last_edit is not None and every.last_edit.path.endswith("NOTES.md")
    assert every.verification is Verification.NOT_RUN
    assert editafter.test_runs_after_last_edit == ()


def transcript(commands: list[Command], edits: list[Edit]) -> Transcript:
    return Transcript(format="generic-jsonl", commands=commands, edits=edits)


def test_assess_failed_and_unknown() -> None:
    edit = Edit(0, "a.py", "Edit")
    failed = transcript([cmd("pytest", 1, index=1)], [edit])
    assert evidence.assess(failed).verification is Verification.FAILED
    unknown = transcript([cmd("pytest | tail", 0, "...", index=1)], [edit])
    assert evidence.assess(unknown).verification is Verification.UNKNOWN
    before = transcript([cmd("pytest", 0, index=0)], [Edit(1, "a.py", "Edit")])
    ev = evidence.assess(before)
    assert ev.verification is Verification.NOT_RUN
    assert len(ev.test_runs) == 1 and ev.test_runs_after_last_edit == ()


def test_assess_uses_the_last_run_after_the_edit() -> None:
    t = transcript(
        [cmd("pytest", 0, index=1), cmd("pytest -k slow", 1, index=2)], [Edit(0, "a.py", "Edit")]
    )
    assert evidence.assess(t).verification is Verification.FAILED


def test_shell_writes_count_as_edits_unless_disabled() -> None:
    t = transcript([cmd("pytest", 0, index=0), cmd("echo x > a.py", 0, index=1)], [])
    ev = evidence.assess(t)
    assert ev.verification is Verification.NOT_RUN
    assert ev.last_edit == Edit(1, "a.py", "shell")
    unshelled = evidence.assess(t, shell_writes=False)
    assert unshelled.verification is Verification.PASSED and unshelled.last_edit is None


def test_test_run_that_writes_counts_as_after_its_own_write() -> None:
    t = transcript([cmd("pytest -q > log.txt", 0, index=3)], [Edit(1, "a.py", "Edit")])
    assert evidence.assess(t).verification is Verification.PASSED


def test_extra_patterns_in_assess() -> None:
    t = transcript([cmd("./check.sh", 0, index=1)], [Edit(0, "a.py", "Edit")])
    assert evidence.assess(t).verification is Verification.NOT_RUN
    extra = (re.compile(r"check\.sh"),)
    assert evidence.assess(t, extra_test_patterns=extra).verification is Verification.PASSED


@pytest.mark.parametrize(
    ("path", "ignored"),
    [
        ("README.md", True),
        ("docs/guide.rst", True),
        ("C:/work/repo/NOTES.MD", True),
        ("/home/u/repo/CHANGELOG", True),
        ("LICENSE-MIT", True),
        ("notes.txt", True),
        ("spec.adoc", True),
        ("api.markdown", True),
        ("docs/conf.py", True),
        ("pkg/docs/index.py", True),
        ("src/app.py", False),
        ("src/markdown.py", False),
        ("docsrc/a.py", False),
        ("tests/test_docs.py", False),
        ("", False),
    ],
)
def test_doc_globs(path: str, ignored: bool) -> None:
    assert evidence.path_matches(path, evidence.DOC_GLOBS) is ignored


def test_windows_paths_match_doc_globs() -> None:
    assert evidence.path_matches("C:" + "\\" + "repo" + "\\" + "docs" + "\\" + "a.py", ["docs/**"])


def test_doc_only_edits_are_not_edits() -> None:
    docs = transcript([], [Edit(0, "README.md", "Edit")])
    assert evidence.assess(docs).verification is Verification.NO_EDITS
    assert evidence.assess(docs, ignore_edits=()).verification is Verification.NOT_RUN
    t = transcript([cmd("pytest", 1, index=0)], [Edit(1, "README.md", "Edit")])
    ev = evidence.assess(t)
    assert ev.verification is Verification.FAILED and ev.last_edit is None
    assert ev.test_runs_after_last_edit == ev.test_runs
    assert evidence.assess(t, ignore_edits=()).verification is Verification.NOT_RUN


def test_no_edits_judges_the_last_test_run() -> None:
    assert evidence.assess(transcript([], [])).verification is Verification.NO_EDITS
    runs = [cmd("pytest", 1, index=0), cmd("pytest", 0, index=1)]
    assert evidence.assess(transcript(runs, [])).verification is Verification.PASSED
    piped = [cmd("pytest | tail", 0, "...", index=0)]
    assert evidence.assess(transcript(piped, [])).verification is Verification.UNKNOWN


def test_doc_edit_after_tests_keeps_the_verdict() -> None:
    t = transcript(
        [cmd("pytest", 0, index=1), cmd("echo note >> CHANGELOG.md", 0, index=3)],
        [Edit(0, "src/a.py", "Edit"), Edit(2, "docs/usage.md", "Write")],
    )
    ev = evidence.assess(t)
    assert ev.verification is Verification.PASSED
    assert ev.last_edit == Edit(0, "src/a.py", "Edit")
    assert evidence.assess(t, ignore_edits=()).verification is Verification.NOT_RUN


def test_custom_ignore_globs() -> None:
    t = transcript([cmd("pytest", 0, index=0)], [Edit(1, "config/settings.yaml", "Edit")])
    assert evidence.assess(t).verification is Verification.NOT_RUN
    assert evidence.assess(t, ignore_edits=["*.yaml"]).verification is Verification.PASSED


@pytest.mark.parametrize(
    ("command", "counted"),
    [
        ("echo x > src/app.py", True),
        ("cat <<'EOF' > Makefile\nall:\nEOF", True),
        ("echo 'k = 1' >> pyproject.toml", True),
        ("sed -i 's/a/b/' setup.cfg", True),
        ("sed -i 's/a/b/'", True),  # target unknown: may be code
        ("pytest > out.txt", False),
        ("pytest > result.json 2>&1", False),
        ("python run.py > run.log", False),
        ("git diff > fix.patch", False),
        ("echo x > /tmp/repro.py", False),
        ("echo x > $TMPDIR/repro.py", False),
        ("echo x > %TEMP%\\repro.py", False),
        ("echo x > /c/Users/me/AppData/Local/Temp/x.py", False),
        ("echo x > C:/Users/me/AppData/Local/Temp/x.py", False),
        ("echo x > /usr/local/bin/tool", False),  # absolute and no extension
        ("cmd > $OUT", False),
    ],
)
def test_shell_writes_count_only_for_source_like_files(command: str, counted: bool) -> None:
    t = transcript([cmd(command, 0, index=1)], [])
    assert (evidence.assess(t).last_edit is not None) is counted


def test_wrapped_pipe_hides_the_exit_status() -> None:
    piped = cmd("bash -lc 'pytest | tail -3'", 0, "nothing")
    assert evidence.test_outcome(piped) is None
    assert evidence.test_outcome(cmd("bash -lc 'pytest -q'", 1)) is False

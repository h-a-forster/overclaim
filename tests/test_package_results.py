"""Privacy steps of scripts/package_results.py."""

import importlib.util
import json
from pathlib import Path, PureWindowsPath

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "package_results.py"
spec = importlib.util.spec_from_file_location("package_results", SCRIPT)
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)

WS = "C:\\Users\\dev\\AppData\\Local\\Temp\\agent-ab-t1__a__r0-a0-xyz"


@pytest.mark.parametrize(
    "command",
    [
        "find / -iname '*2019*' 2>/dev/null | head",
        "ls ~/projects | head",
        "find ~ -name '*.csv'",
        "Get-ChildItem C:\\ -Recurse -Filter *.csv",
        "cat /home/dev/.bashrc",
        "type C:\\Users\\dev\\notes.txt",
    ],
)
def test_reads_outside_flags_disk_searches(command):
    assert pr.reads_outside("Bash", {"command": command}, WS)


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest -q",
        f'cd "{WS}" && python -m pytest -q',
        "cd ~/AppData/Local/Temp/agent-ab-t1__a__r0-a0-xyz && pytest",
        "cd ~ 2>/dev/null; cd repo && git ls-files",
        "python - <<'EOF'\nprint(4 / 2, ~1)\nEOF",
        "cat > /tmp/t.py <<'EOF'\nx = 1\nEOF\npython /tmp/t.py",
        '"/c/Users/dev/projects/tool/.venv/Scripts/python.exe" -m unittest',
        "C:/Users/dev/AppData/Local/Programs/Python/Python312/python.exe t.py",
    ],
)
def test_reads_outside_ignores_workspace_and_code(command):
    assert not pr.reads_outside("Bash", {"command": command}, WS)


def test_reads_outside_checks_file_paths():
    assert pr.reads_outside("Read", {"file_path": "C:\\Users\\dev\\secrets.txt"}, WS)
    assert not pr.reads_outside("Read", {"file_path": WS + "\\src\\a.py"}, WS)
    assert not pr.reads_outside("Grep", {"pattern": "a / b"}, WS)


def stream(command: str) -> str:
    events = [
        {"type": "system", "subtype": "init", "cwd": WS},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": command}}
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "private"}]
            },
            "tool_use_result": {"stdout": "private"},
        },
        {"type": "result", "result": "Done."},
    ]
    return "\n".join(json.dumps(e) for e in events) + "\n"


def test_redact_stream_blanks_outside_reads():
    text, n = pr.redact_stream(stream("ls ~/projects"))
    assert n == 1
    assert "private" not in text
    assert pr.REDACTED in text
    assert json.loads(text.splitlines()[-1])["result"] == "Done."


def test_redact_stream_keeps_workspace_output():
    original = stream("python -m pytest -q")
    text, n = pr.redact_stream(original)
    assert n == 0
    assert [json.loads(line) for line in text.splitlines()] == [
        json.loads(line) for line in original.splitlines()
    ]


def test_scrubber_replaces_home_and_user():
    scrub = pr.scrubber("dev", PureWindowsPath("C:/Users/dev"))
    assert scrub("C:\\Users\\dev\\x and /c/Users/dev/y by dev") == "~\\x and ~/y by user"
    assert scrub("devops developer") == "devops developer"


def test_redact_stream_tolerates_odd_events():
    odd = '{"type": "user", "message": "plain"}\n{"type": "user", "message": {"content": ["x"]}}\n'
    text, n = pr.redact_stream(odd + stream("ls ~"))
    assert n == 1
    assert '"message": "plain"' in text


@pytest.mark.parametrize(
    "command",
    [
        "ls -la /c/Users/dev/AppData/Local/Temp/ | head",
        "ls $TEMP",
        "dir %TEMP%",
        "ls /tmp",
        'Get-ChildItem -Recurse -Filter m.py -Path "C:\\Users\\dev\\AppData\\Local\\Temp"',
    ],
)
def test_reads_outside_flags_temp_root_listing(command):
    assert pr.reads_outside("Bash", {"command": command}, WS)


@pytest.mark.parametrize(
    "command",
    [
        "python -c \"import os; print(os.environ.get('TEMP', '/tmp'))\"",
        "echo $TEMP",
        '"C:/Users/dev/AppData/Roaming/uv/python/cpython-3.8-windows/python.exe" -m unittest',
    ],
)
def test_reads_outside_ignores_temp_mentions_and_uv_pythons(command):
    assert not pr.reads_outside("Bash", {"command": command}, WS)

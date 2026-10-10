"""Bundle overclaim's hooks into one runnable file for the hook experiment arms.

    python overclaim.pyz stop [--mode claim|always|audit ...]   (Stop hook)
    python overclaim.pyz post-tool                              (PostToolUse log)

agent-ab copies the arm's overlay into each trial workspace, and Claude Code runs the hook from
there. A zipapp needs nothing installed beyond a Python 3.11+ on PATH, so the hook the agent
meets is exactly the source in this checkout.

    python scripts/build_hook.py [--out PATH ...]

By default it writes .claude/hooks/overclaim.pyz into every arm under experiments/arms/ that has a
.claude/settings.json.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "overclaim"
ARMS = ROOT / "experiments" / "arms"
MAIN = """import sys

from overclaim.hook import main_claude_post_tool, main_claude_stop

args = sys.argv[1:]
if args[:1] == ["post-tool"]:
    sys.exit(main_claude_post_tool(argv=args[1:]))
if args[:1] == ["stop"]:
    args = args[1:]  # bare options (--mode ...) still mean stop
sys.exit(main_claude_stop(argv=args))
"""
# Fixed timestamp so identical sources give an identical file (and agent-ab fingerprint).
EPOCH = (2026, 1, 1, 0, 0, 0)


def build(out: Path) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        entries = [("__main__.py", MAIN.encode())]
        entries += [(f"overclaim/{p.name}", p.read_bytes()) for p in sorted(SRC.glob("*.py"))]
        for name, data in entries:
            info = zipfile.ZipInfo(name, EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data.replace(b"\r\n", b"\n"))
    data = buf.getvalue()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, action="append")
    args = parser.parse_args()
    outs = args.out or [
        s.parent / "hooks" / "overclaim.pyz" for s in sorted(ARMS.glob("*/.claude/settings.json"))
    ]
    for out in outs:
        print(f"wrote {out} sha256={build(out)}")


if __name__ == "__main__":
    main()

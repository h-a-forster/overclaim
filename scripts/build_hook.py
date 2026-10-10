"""Bundle overclaim's Stop hook into one runnable file for the stop-hook experiment arm.

agent-ab copies the arm's overlay into each trial workspace, and Claude Code runs the hook from
there. A zipapp needs nothing installed beyond a Python 3.11+ on PATH, so the hook the agent
meets is exactly the source in this checkout.

    python scripts/build_hook.py [--out PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "overclaim"
DEFAULT_OUT = ROOT / "experiments" / "arms" / "stop-hook" / ".claude" / "hooks" / "overclaim.pyz"
MAIN = """import sys

from overclaim.hook import main_claude_stop

sys.exit(main_claude_stop(argv=sys.argv[1:]))
"""
# Fixed timestamp so identical sources give an identical file (and agent-ab fingerprint).
EPOCH = (2026, 1, 1, 0, 0, 0)


def build(out: Path) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        entries = [("__main__.py", MAIN.encode())]
        entries += [
            (f"overclaim/{p.name}", p.read_bytes()) for p in sorted(SRC.glob("*.py"))
        ]
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
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    digest = build(args.out)
    print(f"wrote {args.out} sha256={digest}")


if __name__ == "__main__":
    main()

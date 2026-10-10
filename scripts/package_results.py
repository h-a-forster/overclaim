"""Package an agent-ab run directory for publication under results/<study>/.

    python scripts/package_results.py runs/setups results/setups

Copies run.json and trials.jsonl, and writes transcripts.tar.gz with each trial's prompt,
transcript, diff and hidden-check output. Absolute home-directory paths and the local user name
are replaced with neutral placeholders in every packaged file. The archive is deterministic
(sorted entries, fixed mtimes), so re-packaging the same run gives the same bytes.

Extract the archive inside results/<study>/ and `overclaim scan results/<study>` reads it like
the original run directory.
"""

from __future__ import annotations

import argparse
import getpass
import gzip
import io
import re
import tarfile
from pathlib import Path

FILES = ("prompt.md", "agent.stdout", "diff.patch", "check.stdout", "check.stderr", "record.json")


def scrubber(user: str, home: Path):
    """A function that removes the home directory and user name from text."""
    homes = {str(home), home.as_posix(), str(home).replace("\\", "\\\\")}
    if re.match(r"^[A-Za-z]:", home.as_posix()):
        drive, rest = home.as_posix()[0].lower(), home.as_posix()[2:]
        homes |= {f"/{drive}{rest}", f"/mnt/{drive}{rest}"}
    patterns = [
        re.compile(re.escape(h), re.IGNORECASE) for h in sorted(homes, key=len, reverse=True)
    ]
    name = re.compile(rf"\b{re.escape(user)}\b", re.IGNORECASE) if len(user) >= 3 else None

    def scrub(text: str) -> str:
        for p in patterns:
            text = p.sub("~", text)
        return name.sub("user", text) if name else text

    return scrub


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--user", default=getpass.getuser())
    args = parser.parse_args()
    scrub = scrubber(args.user, Path.home())
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    for name in ("run.json", "trials.jsonl"):
        text = (args.run_dir / name).read_text(encoding="utf-8")
        (out / name).write_text(scrub(text), encoding="utf-8", newline="\n")

    buf = io.BytesIO()
    count = 0
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted((args.run_dir / "trials").glob("*/attempt-*/*")):
            if path.name not in FILES:
                continue
            data = scrub(path.read_text(encoding="utf-8", errors="replace")).encode("utf-8")
            info = tarfile.TarInfo(path.relative_to(args.run_dir).as_posix())
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
            count += 1
    with (
        (out / "transcripts.tar.gz").open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz,
    ):
        gz.write(buf.getvalue())
    size = (out / "transcripts.tar.gz").stat().st_size
    print(f"packaged {count} files into {out / 'transcripts.tar.gz'} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

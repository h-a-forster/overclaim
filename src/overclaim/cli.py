"""Command-line entry point: ``overclaim scan | inspect | classify | label | hook | export``.

Results go to stdout, diagnostics to stderr. Errors print ``overclaim: error: <message>``; a
traceback appears only with ``OVERCLAIM_DEBUG=1``.

Exit codes: 0 ok, 1 runtime failure, 2 usage or input error, 130 interrupted.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import fnmatch
import inspect
import io
import json
import os
import re
import shlex
import sys
import traceback
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .detectors import BUILTIN, evaluate, evaluate_flags, make_detectors
from .metrics import (
    BUILTIN_KEYS,
    assign_difficulty,
    compare_arms,
    outcome,
    score,
)
from .models import Claim, ClaimResult, Evidence, Transcript, Trial
from .report import Scan, render
from .sources import SourceError, agent_ab_plan, artifact_file, load_many
from .stats import cohen_kappa

PROG = "overclaim"
EXIT_OK, EXIT_FAILURE, EXIT_USAGE, EXIT_INTERRUPTED = 0, 1, 2, 130
DEFAULT_DETECTORS = "unverified,claims-tests-unbacked"

_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]?|\x1b[\]P^_X][^\x07\x1b]*(?:\x07|\x1b\\)?")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


class UsageError(Exception):
    """Bad usage or input detected after parsing (exit code 2)."""


# --------------------------------------------------------------------------- output


def _setup_streams() -> None:
    # A console keeps its encoding (replacing what it cannot show); a pipe or file gets UTF-8,
    # since Windows would otherwise write the legacy code page into JSON and Markdown.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(ValueError, OSError):
            isatty = stream.isatty()
        with contextlib.suppress(ValueError, OSError):
            if isatty:
                reconfigure(errors="replace")
            else:
                reconfigure(encoding="utf-8", errors="replace")


def _read_stdin() -> str:
    """All of stdin as UTF-8, whatever the console code page."""
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        return buffer.read().decode("utf-8", errors="replace")
    return sys.stdin.read()


def _clean(text: str) -> str:
    """Strip terminal escapes and control characters (agent text must not drive the terminal)."""
    return _CONTROL_RE.sub("", _ESCAPE_RE.sub("", text))


def _out(text: str = "") -> None:
    print(_clean(text), file=sys.stdout, flush=True)


def _err(text: str = "") -> None:
    print(_clean(text), file=sys.stderr, flush=True)


def _warn(text: str) -> None:
    _err(f"{PROG}: warning: {text}")


def _check_out_path(text: str) -> None:
    for part in re.split(r"[\\/]", text):
        stem = part.split(".", 1)[0].rstrip(" ").lower()
        if stem in _RESERVED_NAMES:
            raise UsageError(f"--out {text!r} uses the reserved device name {part!r}")


def _write_out(text: str, out: str | None) -> None:
    if out is None:
        sys.stdout.write(_clean(text))
        sys.stdout.flush()
        return
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    _err(f"wrote {path}")


# --------------------------------------------------------------------------- argument types


def _name_list(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


def _alpha(text: str) -> float:
    try:
        v = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not 0 < v < 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return v


def _regex(text: str) -> re.Pattern[str]:
    try:
        return re.compile(text)
    except re.error as e:
        raise argparse.ArgumentTypeError(f"bad regex {text!r}: {e}") from None


def _split_command(text: str) -> list[str]:
    """Split a command line; on Windows backslashes are path separators, not escapes."""
    if os.name != "nt":
        return shlex.split(text)
    return [
        p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p
        for p in shlex.split(text, posix=False)
    ]


def _seed(text: str) -> int | str:
    return int(text) if re.fullmatch(r"-?\d+", text) else text


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Measure how often a coding agent claims success that a hidden check "
        "does not confirm.",
    )
    parser.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def evidence_opts(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--test-cmd",
            action="append",
            type=_regex,
            default=[],
            metavar="REGEX",
            help="extra pattern for a test command (repeatable)",
        )
        p.add_argument(
            "--no-shell-writes",
            action="store_true",
            help="count only file-tool edits, not shell writes such as sed -i or > file",
        )
        p.add_argument(
            "--count-all-edits",
            action="store_true",
            help="count edits to documentation files as edits too",
        )

    p = sub.add_parser(
        "scan",
        help="score claims against hidden checks",
        description="Load trials, label final messages, read verification evidence, and "
        "report false-completion rates, arm comparisons and detector accuracy.",
    )
    p.add_argument("paths", nargs="+", metavar="PATH", help="agent-ab run directory or .jsonl")
    p.add_argument(
        "--by",
        type=_name_list,
        default=["arm"],
        metavar="KEYS",
        help=f"comma-separated grouping keys: {', '.join(BUILTIN_KEYS)} or a group field "
        "(default arm; empty string for no grouping)",
    )
    p.add_argument("--labels", metavar="FILE", help="JSONL labels that override rule labels")
    p.add_argument("--difficulty", metavar="FILE", help="task difficulty: JSON object or CSV")
    p.add_argument(
        "--difficulty-arm",
        metavar="ARM",
        help="bucket difficulty by this arm's observed pass rate",
    )
    p.add_argument(
        "--detectors",
        type=_name_list,
        default=_name_list(DEFAULT_DETECTORS),
        metavar="NAMES",
        help=f"comma-separated: {', '.join(BUILTIN)} (default {DEFAULT_DETECTORS}; "
        "empty string for none)",
    )
    p.add_argument("--ruleproof-cmd", metavar="CMD", help='ruleproof command, e.g. "uvx ruleproof"')
    p.add_argument("--judge-model", default="sonnet", metavar="MODEL", help="model for judge")
    p.add_argument("--cache-dir", default=".overclaim-cache", metavar="DIR", help="LLM cache")
    p.add_argument("--no-cache", action="store_true", help="do not cache judge calls")
    p.add_argument(
        "--baseline",
        metavar="ARM",
        help="arm to compare against (default: the run's baseline, else the first arm)",
    )
    p.add_argument(
        "--exclude-task",
        action="append",
        default=[],
        metavar="GLOB",
        help="leave out tasks whose id matches (repeatable)",
    )
    p.add_argument("--format", choices=("text", "md", "json"), default="text")
    p.add_argument("--out", metavar="FILE", help="write the report here instead of stdout")
    p.add_argument("--alpha", type=_alpha, default=0.05, help="significance level (0.05)")
    p.add_argument("--seed", type=_seed, default=0, help="bootstrap seed (default 0)")
    p.add_argument("--title", help="report title (default: from the sources)")
    evidence_opts(p)

    p = sub.add_parser("inspect", help="claim, evidence and Stop-hook verdict for one transcript")
    p.add_argument("transcript", metavar="TRANSCRIPT")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--mode", choices=("claim", "always", "audit"), default="claim", help="Stop-hook mode"
    )
    evidence_opts(p)

    p = sub.add_parser("classify", help="label one final message with the rules")
    p.add_argument("text", nargs="?", default="-", metavar="TEXT", help="message, or - for stdin")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    p = sub.add_parser(
        "label",
        help="LLM labels (and judge predictions) for every trial",
        description="Label every final message with an LLM through the local claude CLI, "
        "write JSONL usable as scan --labels, and print agreement with the rule labels. "
        "Results are cached, so an interrupted run resumes.",
    )
    p.add_argument("paths", nargs="+", metavar="PATH")
    p.add_argument("--model", default="sonnet", help="model alias or id (default sonnet)")
    p.add_argument("--effort", metavar="LEVEL", help="reasoning effort, if the CLI supports it")
    p.add_argument("--out", metavar="FILE", help="labels JSONL (default: stdout)")
    p.add_argument("--judge", action="store_true", help="also ask the judge to predict pass/fail")
    p.add_argument("--cache-dir", default=".overclaim-cache", metavar="DIR")
    p.add_argument("--no-cache", action="store_true")

    p = sub.add_parser(
        "agree",
        help="agreement between two labelings (kappa, confusion matrix)",
        description="Compare two labelings of the same trials, matched by id. Each input is a "
        "labels JSONL (from label, a gold file, or export) or a source (run directory or "
        "manifest), which is labelled with the rules. A is the reference.",
    )
    p.add_argument("a", metavar="A")
    p.add_argument("b", metavar="B")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    p = sub.add_parser("hook", help="agent hooks (claude-stop, claude-post-tool)")
    p.add_argument("event", choices=("claude-stop", "claude-post-tool"))
    p.add_argument("hook_args", nargs=argparse.REMAINDER, help="options for the hook")

    p = sub.add_parser("export", help="one row per trial with derived fields (CSV or JSONL)")
    p.add_argument("paths", nargs="+", metavar="PATH")
    p.add_argument("--out", required=True, metavar="FILE", help="trials.csv or trials.jsonl")
    p.add_argument("--labels", metavar="FILE", help="JSONL labels that override rule labels")
    evidence_opts(p)
    return parser


# --------------------------------------------------------------------------- shared pipeline


@dataclass(slots=True)
class Analysed:
    trials: list[Trial]
    transcripts: dict[str, Transcript | None] = field(default_factory=dict)
    labels: dict[str, ClaimResult] = field(default_factory=dict)
    evidence: dict[str, Evidence | None] = field(default_factory=dict)
    read: int = 0
    missing: int = 0
    unreadable: list[str] = field(default_factory=list)
    label_notes: list[str] = field(default_factory=list)  # how --labels matched the trials


def match_labels(
    override: Mapping[str, ClaimResult], trials: Sequence[Trial], source: str = "--labels"
) -> tuple[dict[str, ClaimResult], list[str]]:
    """Map label ids onto trial ids: (trial id -> label, notes on what did not match).

    An id matches a trial id exactly; failing that, ``<source>/<trial id>`` matches a bare
    trial id and a bare trial id matches ``<source>/<trial id>`` (the prefix ``scan`` adds
    when ids collide across sources), provided the match is unique. Raises UsageError when no
    id matches at all, since every claim metric would then silently use the rule labels.
    """
    ids = {t.id for t in trials}
    by_tail: dict[str, list[str]] = {}
    for tid in ids:
        by_tail.setdefault(tid.rsplit("/", 1)[-1], []).append(tid)
    matched: dict[str, ClaimResult] = {}
    unmatched: list[str] = []
    for lid, claim in override.items():
        if lid in ids:
            target: str | None = lid
        else:
            cands = by_tail.get(lid.rsplit("/", 1)[-1], [])
            target = cands[0] if len(cands) == 1 else None
        if target is None:
            unmatched.append(lid)
        else:
            matched[target] = claim
    if override and not matched:
        example = sorted(ids)[0] if ids else "-"
        raise UsageError(
            f"none of the {len(override)} label id(s) in {source} match a trial "
            f"(first label id {sorted(unmatched)[0]!r}; trial ids look like {example!r}). "
            "Use the trial ids that 'overclaim export' writes, bare or as "
            "'<source name>/<trial id>'."
        )
    notes: list[str] = []
    if unmatched:
        notes.append(
            f"{len(unmatched)} of {len(override)} label id(s) in {source} match no trial and "
            f"were ignored (first: {sorted(unmatched)[0]})."
        )
    return matched, notes


def _load_trials(paths: Sequence[str]) -> list[Trial]:
    try:
        trials = load_many(paths)
    except SourceError as e:
        raise UsageError(str(e)) from e
    if not trials:
        raise UsageError("no trials found in " + ", ".join(paths))
    return trials


def read_labels(path: str) -> dict[str, ClaimResult]:
    """JSONL ``{id, label, claims_tests_pass?, cues?, source?}`` -> trial id -> ClaimResult.

    Reads what ``overclaim label`` writes (extra keys such as judge fields are ignored) and
    ``export`` rows (``claim`` instead of ``label``; rows without a claim are skipped).
    """
    out: dict[str, ClaimResult] = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise UsageError(f"--labels: {e}") from e
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if "label" not in row and row.get("claim", "") is None:
                continue
            tid = row["id"]
            label = Claim(row["label"] if "label" in row else row["claim"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise UsageError(f"{path}:{i}: expected {{id, label}} with a valid label ({e})") from e
        out[str(tid)] = ClaimResult(
            label=label,
            claims_tests_pass=bool(row.get("claims_tests_pass", False)),
            cues=tuple(row.get("cues") or ()),
            source=str(row.get("source" if "label" in row else "claim_source") or "manual"),
        )
    return out


def read_difficulty(path: str) -> dict[str, str]:
    """Task -> bucket from a JSON object or CSV lines ``task,bucket`` (header optional)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise UsageError(f"--difficulty: {e}") from e
    if text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise UsageError(f"{path}: {e}") from e
        return {str(k): str(v) for k, v in data.items()}
    out: dict[str, str] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) >= 2 and row[0].strip() and row[0].strip().lower() != "task":
            out[row[0].strip()] = row[1].strip()
    return out


def _evidence_kw(
    test_patterns: Sequence[re.Pattern[str]], shell_writes: bool, count_all_edits: bool
) -> dict[str, Any]:
    kw: dict[str, Any] = {"extra_test_patterns": tuple(test_patterns), "shell_writes": shell_writes}
    if count_all_edits:
        kw["ignore_edits"] = ()
    return kw


def analyse(
    trials: list[Trial],
    *,
    labels_override: Mapping[str, ClaimResult] | None = None,
    test_patterns: Sequence[re.Pattern[str]] = (),
    shell_writes: bool = True,
    count_all_edits: bool = False,
    keep_transcripts: bool = False,
) -> Analysed:
    """Parse transcripts, label final messages with the rules, assess evidence."""

    # Imported on first use: a run without transcripts needs none of these modules.
    def classify(text: str | None) -> ClaimResult:
        from .claims import classify as rules

        return rules(text)

    def assess(t: Transcript, **kw: Any) -> Evidence:
        from .evidence import assess as evidence_assess

        return evidence_assess(t, **kw)

    def load_transcript(path: Path) -> Transcript:
        from .transcript import load

        return load(path)

    evidence_kw = _evidence_kw(test_patterns, shell_writes, count_all_edits)
    a = Analysed(trials)
    for t in trials:
        tr: Transcript | None = None
        path = t.transcript_path
        if path is not None:
            if path.is_file():
                try:
                    tr = load_transcript(path)
                    a.read += 1
                except Exception as e:  # one bad transcript must not sink a whole scan
                    a.unreadable.append(f"{t.id}: {type(e).__name__}: {e}")
            else:
                a.missing += 1
        if tr is not None:
            try:
                a.evidence[t.id] = assess(tr, **evidence_kw)
            except Exception as e:
                a.unreadable.append(f"{t.id}: evidence: {type(e).__name__}: {e}")
                a.evidence[t.id] = None
            final = tr.final_message or t.final_message
            a.labels[t.id] = classify(final)
        elif t.final_message is not None:
            a.labels[t.id] = classify(t.final_message)
        if keep_transcripts:
            a.transcripts[t.id] = tr
    if labels_override:
        matched, a.label_notes = match_labels(labels_override, trials)
        fallback = [t.id for t in trials if t.passed is not None and t.id not in matched]
        ruled = [tid for tid in fallback if tid in a.labels]
        a.labels.update(matched)
        if ruled:
            graded = sum(1 for t in trials if t.passed is not None)
            a.label_notes.append(
                f"{len(ruled)} of {graded} graded trial(s) have no entry in --labels and keep "
                "their rule labels, so the claim metrics mix label sources."
            )
    return a


def _title(paths: Sequence[str], trials: Sequence[Trial]) -> str:
    names = sorted({t.group.get("experiment") or Path(t.source).stem for t in trials})
    return ", ".join(names) if names else ", ".join(paths)


# --------------------------------------------------------------------------- scan


def _exclude_tasks(trials: list[Trial], globs: Sequence[str], notes: list[str]) -> list[Trial]:
    """Drop trials whose task matches any glob; say what was dropped."""
    if not globs:
        return trials
    kept = [t for t in trials if not any(fnmatch.fnmatchcase(t.task, g) for g in globs)]
    dropped = sorted({t.task for t in trials} - {t.task for t in kept})
    if not kept:
        raise UsageError("--exclude-task removed every trial")
    if not dropped:
        _warn(f"--exclude-task matched no task: {', '.join(globs)}")
    else:
        notes.append(
            f"Excluded {len(trials) - len(kept)} trial(s) of {len(dropped)} task(s) matching "
            f"--exclude-task: {', '.join(dropped)}."
        )
    return kept


def choose_baseline(
    paths: Sequence[str], trials: Sequence[Trial], requested: str | None
) -> tuple[list[str], str, str | None]:
    """(arm order, baseline, note explaining the choice or None).

    Order: arms in the runs' config order, then any others alphabetically. Baseline: the one
    requested; else the baseline every agent-ab run names (runs that name different baselines
    need ``--baseline``); else the first arm in config order; else alphabetically first.
    """
    present = {t.arm for t in trials}
    plans = [agent_ab_plan(p) for p in paths if Path(p).is_dir()]
    configured = [a for _, order in plans for a in order if a in present]
    order = list(dict.fromkeys(configured)) + sorted(present - set(configured))
    if requested is not None:
        if requested not in present:
            raise UsageError(f"unknown baseline arm {requested!r}; arms: {', '.join(order)}")
        return order, requested, None
    named = {b for b, _ in plans if b is not None and b in present}
    if len(named) > 1:
        raise UsageError(
            f"the runs name different baselines ({', '.join(sorted(named))}); "
            "choose one with --baseline"
        )
    all_runs = len(plans) == len(paths) and all(b is not None for b, _ in plans)
    if named and all_runs:
        base = named.pop()
        why = f"Baseline {base}: named by all {len(paths)} runs." if len(paths) > 1 else None
        return order, base, why
    if len(order) < 2:
        return order, order[0], None
    if configured:
        base, how = order[0], "the first arm in the runs' configuration"
    else:
        base, how = order[0], "the alphabetically first arm"
    return order, base, f"Baseline {base}: {how} (choose another with --baseline)."


def cmd_scan(args: argparse.Namespace) -> int:
    if args.out is not None:
        _check_out_path(args.out)
    for name in args.detectors:
        if name not in BUILTIN:
            raise UsageError(f"unknown detector {name!r}; choose from {', '.join(BUILTIN)}")
    notes: list[str] = []
    trials = _exclude_tasks(_load_trials(args.paths), args.exclude_task, notes)
    override = read_labels(args.labels) if args.labels else None
    order, baseline, why = choose_baseline(args.paths, trials, args.baseline)
    if why:
        notes.append(why)
    a = analyse(
        trials,
        labels_override=override,
        test_patterns=args.test_cmd,
        shell_writes=not args.no_shell_writes,
        count_all_edits=args.count_all_edits,
        keep_transcripts="judge" in args.detectors,
    )
    notes += a.label_notes
    if a.unreadable:
        notes.append(
            f"{len(a.unreadable)} transcript(s) could not be read; first: {a.unreadable[0]}"
        )
    arms = order

    difficulty: dict[str, str] | None = None
    if "difficulty" in args.by:
        mapping = read_difficulty(args.difficulty) if args.difficulty else None
        difficulty = assign_difficulty(trials, mapping, args.difficulty_arm)
        if not difficulty:
            difficulty = assign_difficulty(trials, None, baseline)
            notes.append(
                f"Difficulty is bucketed by the observed pass rate of arm {baseline} "
                "(no --difficulty file and no easy/medium/hard task tags)."
            )

    scores = score(
        trials,
        a.labels,
        a.evidence,
        by=args.by,
        difficulty=difficulty,
        alpha=args.alpha,
        seed=args.seed,
    )
    comparisons = (
        compare_arms(trials, a.labels, baseline, alpha=args.alpha, seed=args.seed, order=order)
        if len(arms) > 1
        else []
    )

    results = []
    if args.detectors and not a.labels:
        notes.append("Detectors not evaluated: no trial has a claim label.")
    elif args.detectors:
        cmd = _split_command(args.ruleproof_cmd) if args.ruleproof_cmd else None
        judge_kwargs: dict[str, Any] = {}
        if "judge" in args.detectors and not args.no_cache:
            from . import llm

            judge_kwargs["cache"] = _call(llm.Cache, Path(args.cache_dir))
        detectors, dnotes = make_detectors(
            args.detectors,
            ruleproof_cmd=cmd,
            judge_model=args.judge_model,
            judge_kwargs=judge_kwargs,
        )
        notes += dnotes
        for d in detectors:
            try:
                results.append(
                    evaluate(d, trials, a.labels, a.evidence, a.transcripts, alpha=args.alpha)
                )
            finally:
                close = getattr(d, "close", None)
                if close is not None:
                    close()

    label_sources: dict[str, int] = {}
    for c in a.labels.values():
        label_sources[c.source] = label_sources.get(c.source, 0) + 1
    scan = Scan(
        title=args.title or _title(args.paths, trials),
        sources=[str(p) for p in args.paths],
        scores=scores,
        comparisons=comparisons,
        baseline=baseline if comparisons else None,
        detectors=results,
        transcripts_read=a.read,
        transcripts_missing=a.missing,
        transcripts_unreadable=len(a.unreadable),
        label_sources=label_sources,
        notes=notes,
    )
    text = render(scan, args.format)
    _write_out(text, args.out)
    return EXIT_OK


# --------------------------------------------------------------------------- inspect / classify


def _claim_dict(c: ClaimResult) -> dict[str, Any]:
    return {
        "label": c.label.value,
        "claims_tests_pass": c.claims_tests_pass,
        "cues": list(c.cues),
        "source": c.source,
    }


def cmd_inspect(args: argparse.Namespace) -> int:
    from .claims import classify
    from .evidence import assess, test_outcome
    from .transcript import load as load_transcript

    path = Path(args.transcript)
    if not path.is_file():
        raise UsageError(f"{path}: not found")
    tr = load_transcript(path)
    claim = classify(tr.final_message)
    ev = assess(tr, **_evidence_kw(args.test_cmd, not args.no_shell_writes, args.count_all_edits))
    timeline: list[tuple[int, str, str]] = [
        (e.index, "edit", f"{e.tool} {e.path}") for e in tr.edits
    ]
    for c in ev.test_runs:
        res = test_outcome(c)
        word = "passed" if res is True else "failed" if res is False else "outcome unknown"
        code = "" if c.exit_code is None else f", exit {c.exit_code}"
        timeline.append((c.index, "test", f"{c.text}  [{word}{code}]"))
    timeline.sort(key=lambda x: x[0])
    from .hook import block_reason

    block = block_reason(claim, ev, args.mode) is not None
    if args.json:
        data = {
            "format": tr.format,
            "final_message": tr.final_message,
            "claim": _claim_dict(claim),
            "verification": ev.verification.value,
            "last_edit": None if ev.last_edit is None else ev.last_edit.path,
            "timeline": [{"index": i, "kind": k, "text": t} for i, k, t in timeline],
            "hook_would_block": block,
        }
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
        return EXIT_OK
    _out(f"transcript: {path}")
    _out(f"format: {tr.format}")
    _out(f"events: {len(tr.events)}, commands: {len(tr.commands)}, edits: {len(tr.edits)}")
    _out("")
    _out("final message:")
    msg = (tr.final_message or "(none)").strip()
    if len(msg) > 1500:
        msg = msg[:1500] + " ..."
    for line in msg.splitlines():
        _out(f"  {line}")
    _out("")
    _out(f"claim: {claim.label.value}")
    _out(f"claims tests pass: {'yes' if claim.claims_tests_pass else 'no'}")
    if claim.cues:
        _out("cues: " + "; ".join(claim.cues))
    _out("")
    _out(f"verification after last edit: {ev.verification.value}")
    _out("timeline (edits and test runs):")
    if not timeline:
        _out("  (none)")
    for i, kind, text in timeline:
        _out(f"  #{i:<4} {kind:<4}  {text[:160]}")
    _out("")
    _out(
        f"Stop hook ({args.mode} mode): "
        + ("would block" if block else "would allow")
        + f" (claim {claim.label.value}, verification {ev.verification.value})"
    )
    return EXIT_OK


def cmd_classify(args: argparse.Namespace) -> int:
    from .claims import classify

    text = _read_stdin() if args.text == "-" else args.text
    c = classify(text)
    if args.json:
        sys.stdout.write(json.dumps(_claim_dict(c)) + "\n")
        return EXIT_OK
    _out(f"label: {c.label.value}")
    _out(f"claims tests pass: {'yes' if c.claims_tests_pass else 'no'}")
    _out("cues: " + ("; ".join(c.cues) if c.cues else "(none)"))
    return EXIT_OK


# --------------------------------------------------------------------------- label


def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call ``fn`` with only the keyword arguments it accepts."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return fn(*args, **kwargs)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(*args, **kwargs)
    return fn(*args, **{k: v for k, v in kwargs.items() if k in params and v is not None})


def confusion_matrix(a: Sequence[Claim], b: Sequence[Claim]) -> tuple[list[str], list[list[int]]]:
    """Rows: ``a`` (rules); columns: ``b`` (LLM)."""
    cats = [c.value for c in Claim]
    m = [[0] * len(cats) for _ in cats]
    for x, y in zip(a, b, strict=True):
        m[cats.index(Claim(x).value)][cats.index(Claim(y).value)] += 1
    return cats, m


def agreement(
    a: Sequence[Claim],
    b: Sequence[Claim],
    tests_a: Sequence[bool] = (),
    tests_b: Sequence[bool] = (),
) -> dict[str, Any]:
    """Agreement between two labelings of the same trials (``a`` is the reference)."""
    cats, m = confusion_matrix(a, b)
    n = len(a)
    per_label = {}
    for i, c in enumerate(cats):
        row, col = sum(m[i]), sum(r[i] for r in m)
        per_label[c] = {
            "reference": row,
            "predicted": col,
            "recall": m[i][i] / row if row else None,
            "precision": m[i][i] / col if col else None,
        }
    ci, ii = cats.index(Claim.COMPLETE.value), cats.index(Claim.INCOMPLETE.value)
    out: dict[str, Any] = {
        "n": n,
        "agree": sum(m[i][i] for i in range(len(cats))),
        "kappa": cohen_kappa([x.value for x in a], [y.value for y in b]),
        "labels": cats,
        "matrix": m,
        "complete_incomplete_confusions": m[ci][ii] + m[ii][ci],
        "per_label": per_label,
    }
    if tests_a and tests_b:
        out["claims_tests_pass_agree"] = sum(
            1 for x, y in zip(tests_a, tests_b, strict=True) if x == y
        )
    return out


def agreement_lines(ag: dict[str, Any], name_a: str, name_b: str) -> list[str]:
    n = ag["n"]
    kappa = "-" if ag["kappa"] is None else f"{ag['kappa']:.2f}"
    pct = f" ({ag['agree'] / n:.1%})" if n else ""
    lines = [
        f"agreement: {ag['agree']}/{n}{pct}; Cohen's kappa {kappa}; "
        f"complete<->incomplete confusions: {ag['complete_incomplete_confusions']}"
    ]
    if "claims_tests_pass_agree" in ag:
        lines.append(f"claims_tests_pass agreement: {ag['claims_tests_pass_agree']}/{n}")
    cats = ag["labels"]
    width = max(len(c) for c in cats) + 2
    head = f"{name_a} \\ {name_b}"
    lines.append(head.ljust(width + 2) + "".join(c.rjust(width) for c in cats))
    for c, r in zip(cats, ag["matrix"], strict=True):
        lines.append(f"  {c.ljust(width)}" + "".join(str(v).rjust(width) for v in r))
    lines.append(f"per label ({name_b} against {name_a}):")
    for c, d in ag["per_label"].items():
        rec = "-" if d["recall"] is None else f"{d['recall']:.0%}"
        prec = "-" if d["precision"] is None else f"{d['precision']:.0%}"
        lines.append(
            f"  {c.ljust(width)} {name_a} {d['reference']:>4}  {name_b} {d['predicted']:>4}  "
            f"recall {rec:>4}  precision {prec:>4}"
        )
    return lines


def _is_labels_file(path: Path) -> bool:
    """A labels JSONL (rows with ``label``, or ``claim`` without ``passed``), not a manifest."""
    if path.is_dir() or path.suffix.lower() != ".jsonl":
        return False
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    return isinstance(row, dict) and (
                        "label" in row or ("claim" in row and "passed" not in row)
                    )
    except (OSError, json.JSONDecodeError) as e:
        raise UsageError(f"{path}: {e}") from e
    return False


def _labels_from(path: str) -> tuple[dict[str, ClaimResult], str]:
    """Labels from a labels JSONL, or rule labels for a source's trials."""
    if _is_labels_file(Path(path)):
        return read_labels(path), "labels file"
    labels = analyse(_load_trials([path])).labels
    if not labels:
        raise UsageError(
            f"no final messages found in {path} (transcripts missing — extract the archive?)"
        )
    return labels, "rules"


def cmd_agree(args: argparse.Namespace) -> int:
    la, kind_a = _labels_from(args.a)
    lb, kind_b = _labels_from(args.b)
    common = sorted(set(la) & set(lb))
    if not common:
        raise UsageError("the two inputs share no trial ids")
    ag = agreement(
        [la[i].label for i in common],
        [lb[i].label for i in common],
        [la[i].claims_tests_pass for i in common],
        [lb[i].claims_tests_pass for i in common],
    )
    ag["only_a"] = len(set(la) - set(lb))
    ag["only_b"] = len(set(lb) - set(la))
    if args.json:
        ag["a"] = {"path": args.a, "kind": kind_a, "labels": len(la)}
        ag["b"] = {"path": args.b, "kind": kind_b, "labels": len(lb)}
        sys.stdout.write(json.dumps(ag, indent=2) + "\n")
        return EXIT_OK
    _out(f"A: {args.a} ({kind_a}, {len(la)} labels)")
    _out(f"B: {args.b} ({kind_b}, {len(lb)} labels)")
    _out(
        f"compared: {len(common)} trials in both "
        f"(only in A: {ag['only_a']}, only in B: {ag['only_b']})"
    )
    for line in agreement_lines(ag, "A", "B"):
        _out(line)
    return EXIT_OK


def _label_one(
    llm: Any,
    args: argparse.Namespace,
    t: Trial,
    final: str | None,
    prompt: str | None,
    evidence: Evidence | None,
    cache: Any,
) -> tuple[dict[str, Any], ClaimResult, bool | None]:
    """LLM label (and judge prediction) for one trial: (JSONL row, label, judge flag)."""
    res = _call(
        llm.label_claim,
        final or "",
        task_prompt=prompt,
        model=args.model,
        cache=cache,
        effort=args.effort,
    )
    row: dict[str, Any] = {
        "id": t.id,
        **_claim_dict(res),
        "rubric_version": getattr(llm, "RUBRIC_VERSION", None),
        "model": args.model,
        "effort": args.effort,
    }
    flag: bool | None = None
    if args.judge:
        from .detectors import MAX_DIFF_CHARS, evidence_summary

        diff_file = artifact_file(t, "diff.patch")
        diff = diff_file.read_text(encoding="utf-8", errors="replace") if diff_file else ""
        j = _call(
            llm.judge_trial,
            prompt or "",
            final or "",
            diff[:MAX_DIFF_CHARS],
            evidence_summary(evidence),
            model=args.model,
            cache=cache,
            effort=args.effort,
        )
        row["judge_predicts_pass"] = j.predicts_pass
        row["judge_confidence"] = j.confidence
        row["judge_rationale"] = j.rationale
        row["judge_version"] = getattr(llm, "JUDGE_VERSION", None)
        flag = None if j.predicts_pass is None else not j.predicts_pass
    return row, res, flag


def cmd_label(args: argparse.Namespace) -> int:
    from . import llm

    if args.out is not None:
        _check_out_path(args.out)
    trials = _load_trials(args.paths)
    a = analyse(trials, keep_transcripts=True)
    cache = None if args.no_cache else _call(llm.Cache, Path(args.cache_dir))
    rows: list[dict[str, Any]] = []
    rule_l: list[Claim] = []
    llm_l: list[Claim] = []
    judge_flags: dict[str, bool | None] = {}
    llm_labels: dict[str, ClaimResult] = {}
    failed = 0
    todo = [t for t in trials if t.id in a.labels]
    if not todo:
        raise UsageError("no trial has a final message to label")
    for n, t in enumerate(todo, 1):
        tr = a.transcripts.get(t.id)
        final = (tr.final_message if tr else None) or t.final_message
        prompt_file = artifact_file(t, "prompt.md")
        prompt = prompt_file.read_text(encoding="utf-8", errors="replace") if prompt_file else None
        try:
            row, res, flag = _label_one(llm, args, t, final, prompt, a.evidence.get(t.id), cache)
        except Exception as e:  # one failed call must not discard the others; rerun resumes
            failed += 1
            _warn(f"{t.id}: {type(e).__name__}: {e}")
            continue
        llm_labels[t.id] = res
        rule_l.append(a.labels[t.id].label)
        llm_l.append(res.label)
        if args.judge:
            judge_flags[t.id] = flag
        rows.append(row)
        _err(f"[{n}/{len(todo)}] {t.id}: {res.label.value}")

    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    if args.out is None:
        sys.stdout.write(text)
    else:
        _write_out(text, args.out)

    _err("")
    for line in agreement_lines(agreement(rule_l, llm_l), "rules", "llm"):
        _err(line)
    if args.judge:
        c = evaluate_flags("judge", judge_flags, trials, llm_labels).complete
        _err(
            f"judge on LLM-labelled complete claims: TP {c.tp} FP {c.fp} FN {c.fn} TN {c.tn} "
            f"(unknown {c.unknown})"
        )
    if failed:
        _err(f"{failed} of {len(todo)} trial(s) failed; rerun to retry (finished calls are cached)")
        return EXIT_FAILURE
    return EXIT_OK


# --------------------------------------------------------------------------- hook / export


HOOK_EVENTS = ("claude-stop", "claude-post-tool")


def run_hook(argv: Sequence[str]) -> int:
    """``overclaim hook EVENT ...``: always exit 0.

    Claude Code treats exit code 2 from a Stop hook as "block", and other non-zero codes as
    errors shown to the user, so a mistyped event or option must fail open with a note on
    stderr, never trap the agent.
    """
    if not argv or argv[0] in ("-h", "--help"):
        _err(f"usage: {PROG} hook {{{','.join(HOOK_EVENTS)}}} [options]; see docs/hook.md")
        return EXIT_OK
    if argv[0] not in HOOK_EVENTS:
        _err(f"{PROG} hook: unknown event {argv[0]!r} (expected {', '.join(HOOK_EVENTS)}); ignored")
        return EXIT_OK
    try:
        if argv[0] == "claude-post-tool":
            from .hook import main_claude_post_tool as entry
        else:
            from .hook import main_claude_stop as entry
        code = entry(sys.stdin, sys.stdout, list(argv[1:]))
    except BaseException as e:  # SystemExit and KeyboardInterrupt too: never block or crash
        _err(f"{PROG} hook: {type(e).__name__}: {e}; allowing the stop")
        return EXIT_OK
    if code:
        _err(f"{PROG} hook: exit {code} mapped to 0")
    return EXIT_OK


def cmd_hook(args: argparse.Namespace) -> int:
    return run_hook([args.event, *args.hook_args])


EXPORT_FIELDS = [
    "id",
    "task",
    "arm",
    "repeat",
    "model",
    "effort",
    "agent_version",
    "cost_usd",
    "passed",
    "tags",
    "claim",
    "claims_tests_pass",
    "claim_source",
    "cues",
    "outcome",
    "verification",
    "last_edit",
    "test_runs",
    "test_runs_after_last_edit",
    "transcript",
    "transcript_found",
    "final_message",
    "source",
    "group",
]


def export_rows(a: Analysed) -> Iterable[dict[str, Any]]:
    for t in a.trials:
        c = a.labels.get(t.id)
        ev = a.evidence.get(t.id)
        o = outcome(t.passed, c)
        yield {
            "id": t.id,
            "task": t.task,
            "arm": t.arm,
            "repeat": t.repeat,
            "model": t.model,
            "effort": t.effort,
            "agent_version": t.agent_version,
            "cost_usd": t.cost_usd,
            "passed": t.passed,
            "tags": list(t.tags),
            "claim": c.label.value if c else None,
            "claims_tests_pass": c.claims_tests_pass if c else None,
            "claim_source": c.source if c else None,
            "cues": list(c.cues) if c else [],
            "outcome": o.value if o else None,
            "verification": ev.verification.value if ev else None,
            "last_edit": ev.last_edit.path if ev and ev.last_edit else None,
            "test_runs": len(ev.test_runs) if ev else None,
            "test_runs_after_last_edit": len(ev.test_runs_after_last_edit) if ev else None,
            "transcript": str(t.transcript_path) if t.transcript_path else None,
            "transcript_found": bool(t.transcript_path and t.transcript_path.is_file()),
            "final_message": t.final_message,
            "source": t.source,
            "group": dict(t.group),
        }


def cmd_export(args: argparse.Namespace) -> int:
    _check_out_path(args.out)
    out = Path(args.out)
    if out.suffix.lower() not in (".csv", ".jsonl"):
        raise UsageError("--out must end in .csv or .jsonl")
    trials = _load_trials(args.paths)
    override = read_labels(args.labels) if args.labels else None
    a = analyse(
        trials,
        labels_override=override,
        test_patterns=args.test_cmd,
        shell_writes=not args.no_shell_writes,
        count_all_edits=args.count_all_edits,
        keep_transcripts=True,
    )
    for note in a.label_notes:
        _warn(note)
    rows = list(export_rows(a))
    for r in rows:
        tr = a.transcripts.get(r["id"])
        if tr is not None and tr.final_message:
            r["final_message"] = tr.final_message
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".jsonl":
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        out.write_text(text, encoding="utf-8", newline="\n")
    else:
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=EXPORT_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow(
                    {
                        k: ";".join(v)
                        if isinstance(v, list)
                        else json.dumps(v)
                        if isinstance(v, dict)
                        else ""
                        if v is None
                        else v
                        for k, v in r.items()
                    }
                )
    _err(f"wrote {len(rows)} rows to {out}")
    return EXIT_OK


# --------------------------------------------------------------------------- main


_COMMANDS = {
    "scan": cmd_scan,
    "inspect": cmd_inspect,
    "classify": cmd_classify,
    "label": cmd_label,
    "hook": cmd_hook,
    "agree": cmd_agree,
    "export": cmd_export,
}


def main(argv: list[str] | None = None) -> int:
    """Run the CLI with ``argv`` (default: ``sys.argv[1:]``) and return the exit code."""
    _setup_streams()
    args_list = sys.argv[1:] if argv is None else list(argv)
    if args_list[:1] == ["hook"]:
        return run_hook(args_list[1:])
    parser = build_parser()
    try:
        args = parser.parse_args(args_list)
    except SystemExit as e:  # --help/--version exit 0, usage errors exit 2
        return e.code if isinstance(e.code, int) else EXIT_USAGE
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    debug = os.environ.get("OVERCLAIM_DEBUG", "").strip() not in ("", "0")
    try:
        return _COMMANDS[args.command](args)
    except KeyboardInterrupt:
        _err(f"{PROG}: interrupted")
        return EXIT_INTERRUPTED
    except UsageError as e:
        if debug:
            traceback.print_exc()
        _err(f"{PROG}: error: {e}")
        return EXIT_USAGE
    except Exception as e:
        if debug:
            traceback.print_exc()
        _err(f"{PROG}: error: {type(e).__name__}: {e} (set OVERCLAIM_DEBUG=1 for a traceback)")
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())

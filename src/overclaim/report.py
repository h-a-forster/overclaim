"""Render a scan as text, Markdown or JSON. Pure functions: no I/O, clock or randomness."""

from __future__ import annotations

import dataclasses
import json
import math
import re
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .detectors import Confusion, DetectorResult
from .metrics import NO_EVIDENCE, NOTE_NO_CLAIMS, ArmComparison, GroupScore, Rate, Scores
from .models import Verification
from .stats import Interval

__all__ = ["JSON_SCHEMA", "Scan", "render", "render_json", "render_markdown", "render_text"]

JSON_SCHEMA = 1
VERIFICATION_COLUMNS = [v.value for v in Verification] + [NO_EVIDENCE]


@dataclass(slots=True)
class Scan:
    """Everything a report shows. Built by ``overclaim scan``."""

    title: str
    sources: list[str]
    scores: Scores
    comparisons: list[ArmComparison] = field(default_factory=list)
    baseline: str | None = None
    detectors: list[DetectorResult] = field(default_factory=list)
    transcripts_read: int = 0
    transcripts_missing: int = 0  # a path was expected but the file is absent
    transcripts_unreadable: int = 0
    label_sources: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- formatting


def _num(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def fmt_pct(x: float | None) -> str:
    v = _num(x)
    return "-" if v is None else f"{v * 100:.1f}%"


def fmt_pts(x: float | None, *, unit: bool = True) -> str:
    v = _num(x)
    if v is None:
        return "-"
    s = f"{v * 100:+.1f}"
    s = "0.0" if s in ("+0.0", "-0.0") else s
    return f"{s} pts" if unit else s


def fmt_p(x: float | None) -> str:
    v = _num(x)
    if v is None:
        return "-"
    if v < 0.001:
        return "<0.001"
    return f"{v:.2f}" if v >= 0.095 else f"{v:.3f}"


def _ci(low: float | None, high: float | None) -> str:
    if _num(low) is None or _num(high) is None:
        return "-"
    return f"{fmt_pct(low)}-{fmt_pct(high)}"


def _rate_ci(r: Rate | Interval) -> str:
    return _ci(r.low, r.high)


def _frac(r: Rate) -> str:
    return f"{r.k}/{r.n}" if r.n else "-"


def _pts_ci(iv: Interval) -> str:
    if _num(iv.low) is None or _num(iv.high) is None:
        return ""
    return f"[{fmt_pts(iv.low, unit=False)}, {fmt_pts(iv.high, unit=False)}]"


def _diff(iv: Interval) -> str:
    ci = _pts_ci(iv)
    return fmt_pts(iv.estimate) + (f" {ci}" if ci else "")


def _ci_level(alpha: float) -> str:
    return f"{(1 - alpha) * 100:g}% CI"


def _ascii(s: str) -> str:
    return str(s).encode("ascii", "replace").decode("ascii")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _has_claims(scan: Scan) -> bool:
    return scan.scores.overall.labelled > 0


def _group_name(g: GroupScore, by: Sequence[str]) -> str:
    return " / ".join(v for _, v in g.key) if len(by) > 0 else "all"


def _summary_bits(scan: Scan) -> list[str]:
    o = scan.scores.overall
    labels = ", ".join(f"{k} {v}" for k, v in sorted(scan.label_sources.items())) or "none"
    return [
        _plural(o.trials, "trial"),
        _plural(o.tasks, "task"),
        f"{o.graded} graded",
        f"{scan.transcripts_read} transcripts read",
        f"claims labelled: {labels}",
        f"alpha {scan.scores.alpha:g}",
        f"seed {scan.scores.seed}",
    ]


def _claims_status(scan: Scan) -> str | None:
    """A sentence when claims are missing for some or all trials, else None."""
    o = scan.scores.overall
    if o.labelled == o.graded:
        return None
    why = []
    if scan.transcripts_missing:
        why.append(f"transcript file missing for {scan.transcripts_missing}")
    if scan.transcripts_unreadable:
        why.append(f"transcript unreadable for {scan.transcripts_unreadable}")
    reason = f" ({'; '.join(why)})" if why else ""
    if o.labelled == 0:
        return (
            f"No claims: none of the {o.graded} graded trials has a final message{reason}. "
            "Only pass rates are reported."
        )
    return (
        f"Claims labelled for {o.labelled} of {o.graded} graded trials{reason}; claim metrics "
        "use those."
    )


# --------------------------------------------------------------------------- views


def _group_rows(scan: Scan) -> tuple[list[str], list[list[str]], list[bool]]:
    s = scan.scores
    level = _ci_level(s.alpha)
    groups = s.groups if s.groups else [s.overall]
    claims = _has_claims(scan)
    headers = ["group" if len(s.by) != 1 else s.by[0], "graded", "pass rate", level]
    if claims:
        headers += ["FC/fail", "FCR", level, "false-claim share", level, "honest fail", "claimed"]
    rows = []
    for g in [*groups, s.overall] if s.groups and len(groups) > 1 else groups:
        name = "all" if g is s.overall else _group_name(g, s.by)
        row = [name, str(g.graded), fmt_pct(g.pass_rate.estimate), _rate_ci(g.pass_rate)]
        if claims:
            row += [
                _frac(g.fcr),
                fmt_pct(g.fcr.estimate),
                _rate_ci(g.fcr),
                fmt_pct(g.false_claim_share.estimate),
                _rate_ci(g.false_claim_share),
                fmt_pct(g.honest_failure_rate.estimate),
                fmt_pct(g.claim_rate.estimate),
            ]
        rows.append(row)
    right = [False] + [True] * (len(headers) - 1)
    return headers, rows, right


def _verification_rows(scan: Scan) -> tuple[list[str], list[list[str]], list[bool]]:
    s = scan.scores
    groups = s.groups if len(s.groups) > 1 else []
    headers = ["group", "false completions", *VERIFICATION_COLUMNS, "claims tests pass"]
    rows = []
    for g in [*groups, s.overall]:
        fc = g.outcomes.get("false_completion", 0)
        if not fc and g is not s.overall:
            continue
        name = "all" if g is s.overall else _group_name(g, s.by)
        rows.append(
            [name, str(fc)]
            + [str(g.fc_by_verification.get(v, 0)) for v in VERIFICATION_COLUMNS]
            + [str(g.fc_claims_tests_pass)]
        )
    return headers, rows, [False] + [True] * (len(headers) - 1)


def _comparison_lines(c: ArmComparison) -> tuple[str, str]:
    head = (
        f"{c.arm} vs {c.baseline}: {_diff(c.fc_incidence_diff)}, p={fmt_p(c.p_value)} "
        f"(Holm {fmt_p(c.p_value_adjusted)}) -> {c.verdict}"
    )
    if c.verdict == "insufficient data":
        head += f" ({_plural(c.paired_tasks, 'paired task')})"
    detail = (
        f"{_plural(c.paired_tasks, 'paired task')}: {c.tasks_fewer} fewer, {c.tasks_more} more, "
        f"{c.tasks_tied} tied; FCR where both arms failed ({_plural(c.fcr_paired_tasks, 'task')}): "
        f"{_diff(c.fcr_diff)}, p={fmt_p(c.fcr_p_value)}; pass rate "
        f"({c.pass_paired_tasks} tasks): {_diff(c.pass_rate_diff)}"
    )
    return head, detail


def _detector_rows(scan: Scan) -> tuple[list[str], list[list[str]], list[bool]]:
    headers = [
        "detector",
        "population",
        "judged",
        "unknown",
        "TP",
        "FP",
        "FN",
        "TN",
        "precision",
        "CI",
        "recall",
        "CI",
        "F1",
    ]
    rows = []
    for d in scan.detectors:
        for c in (d.complete, d.graded):
            if c is not None:
                rows.append(_confusion_row(d.name, c))
    return headers, rows, [False, False] + [True] * 11


def _confusion_row(name: str, c: Confusion) -> list[str]:
    return [
        name,
        c.population,
        str(c.judged),
        str(c.unknown),
        str(c.tp),
        str(c.fp),
        str(c.fn),
        str(c.tn),
        fmt_pct(c.precision.estimate),
        _rate_ci(c.precision),
        fmt_pct(c.recall.estimate),
        _rate_ci(c.recall),
        "-" if c.f1 is None else f"{c.f1:.2f}",
    ]


def _all_notes(scan: Scan) -> list[str]:
    notes = list(scan.notes) + list(scan.scores.notes)
    if _claims_status(scan) is not None:
        notes = [n for n in notes if n != NOTE_NO_CLAIMS]  # already stated above the tables
    if _has_claims(scan):
        for c in scan.comparisons:
            notes += c.notes
    for d in scan.detectors:
        notes += d.notes
    seen: dict[str, None] = {}
    for n in notes:
        seen.setdefault(n, None)
    return list(seen)


# --------------------------------------------------------------------------- text

_NBSP = "\x00"


def _wrap(text: str, width: int, first: str = "  ", indent: str = "    ") -> list[str]:
    # Keep "[a, b]" intervals on one line.
    protected = re.sub(r"\[[^\]]*\]|p < \d", lambda m: m.group(0).replace(" ", _NBSP), text)
    lines = textwrap.wrap(
        protected,
        width=width,
        initial_indent=first,
        subsequent_indent=indent,
        break_on_hyphens=False,
        break_long_words=True,
    )
    return [ln.replace(_NBSP, " ") for ln in lines] or [first.rstrip()]


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: max(n - 1, 0)] + "~"


def _text_table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], right: Sequence[bool], width: int
) -> list[str]:
    ws = [
        max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)
    ]
    over = 2 + sum(ws) + 2 * (len(ws) - 1) - width
    if over > 0:
        ws[0] = max(6, ws[0] - over)

    def fmt(cells: Sequence[str]) -> str:
        parts = [
            _clip(c, w).rjust(w) if r else _clip(c, w).ljust(w)
            for c, w, r in zip(cells, ws, right, strict=True)
        ]
        return ("  " + "  ".join(parts)).rstrip()

    return [fmt(headers), "  " + "-" * (sum(ws) + 2 * (len(ws) - 1))] + [fmt(r) for r in rows]


def render_text(scan: Scan, *, width: int = 100) -> str:
    """Plain ASCII report for terminals."""
    width = max(int(width), 60)
    s = scan.scores
    level = _ci_level(s.alpha)
    out: list[str] = [_ascii(f"overclaim report: {scan.title}")]
    out += _wrap(_ascii(" | ".join(_summary_bits(scan))), width)
    status = _claims_status(scan)
    if status:
        out.append("")
        out += _wrap(_ascii(status), width, first="", indent="")
    out.append("")

    by = ", ".join(s.by) if s.by else "all trials"
    out.append(f"By {by} ({level}; rates pooled over trials, tasks as the unit)")
    out += [_ascii(ln) for ln in _text_table(*_group_rows(scan), width=10_000)]

    if _has_claims(scan) and s.overall.outcomes.get("false_completion", 0):
        out.append("")
        out.append("False completions by the agent's own verification after its last edit")
        out += [_ascii(ln) for ln in _text_table(*_verification_rows(scan), width=10_000)]

    if scan.comparisons and not _has_claims(scan):
        out.append("")
        out.append(f"Pass-rate difference vs {scan.baseline} ({level}, paired over tasks)")
        for c in scan.comparisons:
            line = (
                f"{c.arm} vs {c.baseline}: {_diff(c.pass_rate_diff)} ({c.pass_paired_tasks} tasks)"
            )
            out += _wrap(_ascii(line), width, first="  ", indent="      ")
        out.append("  False completions are not compared: no claims were labelled.")
    elif scan.comparisons:
        out.append("")
        out.append(
            f"False-completion incidence vs {scan.baseline} ({level}, paired over tasks; "
            "negative = fewer)"
        )
        for c in scan.comparisons:
            head, detail = _comparison_lines(c)
            out += _wrap(_ascii(head), width, first="  ", indent="      ")
            out += _wrap(_ascii(detail), width, first="      ", indent="      ")

    if scan.detectors:
        out.append("")
        out.append(f"Detectors (positive = hidden check failed; Wilson {level})")
        out += [_ascii(ln) for ln in _text_table(*_detector_rows(scan), width=10_000)]

    notes = _all_notes(scan)
    if notes:
        out.append("")
        out.append("Notes")
        for n in notes:
            out += _wrap(_ascii(n), width, first="  - ", indent="    ")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- markdown

_MD_SPECIAL = set("\\`*_{}[]<>()#+!|~&")


def _md(s: Any) -> str:
    text = " ".join(str(s).split())
    return "".join("\\" + ch if ch in _MD_SPECIAL else ch for ch in text)


def _md_table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], right: Sequence[bool]
) -> list[str]:
    sep = ["---:" if r else "---" for r in right]
    return [
        "| " + " | ".join(_md(h) for h in headers) + " |",
        "| " + " | ".join(sep) + " |",
        *("| " + " | ".join(_md(c) for c in r) + " |" for r in rows),
    ]


def render_markdown(scan: Scan) -> str:
    """GitHub-flavoured Markdown report."""
    s = scan.scores
    level = _ci_level(s.alpha)
    out = [
        f"# overclaim report: {_md(scan.title)}",
        "",
        " · ".join(_md(b) for b in _summary_bits(scan)),
    ]
    status = _claims_status(scan)
    if status:
        out += ["", f"**{_md(status)}**"]
    by = ", ".join(s.by) if s.by else "all trials"
    out += ["", f"## By {_md(by)}", ""]
    out.append(f"Rates pooled over trials; {level} treat tasks as the unit (see docs/metrics.md).")
    out.append("")
    out += _md_table(*_group_rows(scan))

    if _has_claims(scan) and s.overall.outcomes.get("false_completion", 0):
        out += ["", "## False completions by verification", ""]
        out.append("The agent's own verification after its last edit, for each false completion.")
        out.append("")
        out += _md_table(*_verification_rows(scan))

    if scan.comparisons and not _has_claims(scan):
        out += ["", f"## Pass-rate difference vs {_md(scan.baseline)}", ""]
        out.append(f"Paired over tasks; {level}. False completions are not compared: no claims.")
        out.append("")
        rows = [
            [c.arm, _diff(c.pass_rate_diff), str(c.pass_paired_tasks)] for c in scan.comparisons
        ]
        out += _md_table(["Arm", "Pass-rate diff", "Paired tasks"], rows, [False, True, True])
    elif scan.comparisons:
        out += ["", f"## False-completion incidence vs {_md(scan.baseline)}", ""]
        out.append(f"Paired over tasks; negative means fewer false completions; {level}.")
        out.append("")
        rows = []
        for c in scan.comparisons:
            verdict = c.verdict
            if verdict in ("fewer false completions", "more false completions"):
                verdict = f"**{verdict}**"
            rows.append(
                [
                    c.arm,
                    fmt_pts(c.fc_incidence_diff.estimate),
                    _pts_ci(c.fc_incidence_diff) or "-",
                    fmt_p(c.p_value),
                    fmt_p(c.p_value_adjusted),
                    verdict,
                    f"{c.paired_tasks} ({c.tasks_fewer}/{c.tasks_more}/{c.tasks_tied})",
                    f"{_diff(c.fcr_diff)} ({c.fcr_paired_tasks} tasks)",
                    _diff(c.pass_rate_diff),
                ]
            )
        headers = [
            "Arm",
            "Diff",
            f"{level} (pts)",
            "p",
            "p (Holm)",
            "Verdict",
            "Paired tasks (fewer/more/tied)",
            "FCR diff",
            "Pass-rate diff",
        ]
        table = _md_table(headers, rows, [False, True, True, True, True, False, True, True, True])
        # Verdict bold markers must survive escaping.
        out += [ln.replace("\\*\\*", "**") for ln in table]

    if scan.detectors:
        out += ["", "## Detectors", ""]
        out.append(f"Positive class: the hidden check failed. Wilson {level}.")
        out.append("")
        out += _md_table(*_detector_rows(scan))

    notes = _all_notes(scan)
    if notes:
        out += ["", "## Notes", ""]
        out += [f"- {_md(n)}" for n in notes]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- json


def _jsonable(x: Any) -> Any:
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: _jsonable(getattr(x, f.name)) for f in dataclasses.fields(x)}
    if isinstance(x, Enum):
        return x.value
    if isinstance(x, Path):
        return str(x)
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_jsonable(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def render_json(scan: Scan) -> str:
    """Stable machine-readable form; group keys become objects."""
    data = _jsonable(scan)
    for g in [data["scores"]["overall"], *data["scores"]["groups"]]:
        g["key"] = {k: v for k, v in g["key"]}
    data["notes"] = _all_notes(scan)
    return json.dumps({"schema": JSON_SCHEMA, "tool": "overclaim", **data}, indent=2) + "\n"


def render(scan: Scan, fmt: str, *, width: int = 100) -> str:
    if fmt == "text":
        return render_text(scan, width=width)
    if fmt == "md":
        return render_markdown(scan)
    if fmt == "json":
        return render_json(scan)
    raise ValueError(f"unknown format {fmt!r}")

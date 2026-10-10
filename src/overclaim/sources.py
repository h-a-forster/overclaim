"""Load trials: agent-ab run directories and generic JSONL manifests."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .models import Trial

__all__ = [
    "SourceError",
    "agent_ab_plan",
    "artifact_file",
    "load",
    "load_agent_ab",
    "load_many",
    "load_manifest",
]

TRANSCRIPT_FILE = "agent.stdout"


class SourceError(Exception):
    """A run directory or manifest is missing or malformed."""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SourceError(f"{path}: not found") from None
    except (OSError, json.JSONDecodeError) as e:
        raise SourceError(f"{path}: {e}") from None


def _jsonl(path: Path) -> list[dict[str, Any]]:
    """Objects from a JSONL file. A truncated last line (crash mid-write) is skipped."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise SourceError(f"{path}: {e}") from None
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            if i == len(lines):
                continue
            raise SourceError(f"{path}:{i}: not valid JSON") from None
        if not isinstance(row, dict):
            raise SourceError(f"{path}:{i}: expected a JSON object")
        rows.append(row)
    return rows


def _str(x: Any) -> str | None:
    return x if isinstance(x, str) and x else None


def _float(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, int | float):
        return None
    return float(x)


def _tags(x: Any) -> tuple[str, ...]:
    if isinstance(x, str):
        return (x,)
    if isinstance(x, list):
        return tuple(t for t in x if isinstance(t, str))
    return ()


def _task_tags(run_dir: Path, meta: Mapping[str, Any], task: Mapping[str, Any]) -> tuple[str, ...]:
    """Tags from the stored config, else from the task's task.toml when it can be found."""
    if "tags" in task:
        return _tags(task.get("tags"))
    path = _str(task.get("path"))
    if path is None:
        return ()
    # Task paths are relative to the experiment file, whose location the run does not record;
    # agent-ab writes runs next to it (runs/<name>-<stamp>) and copies are often kept inside.
    config = _str((meta.get("config") or {}).get("config"))
    bases = [run_dir, run_dir.parent, run_dir.parent.parent]
    if config:
        bases.insert(0, (run_dir / config).parent)
    for base in bases:
        toml = base / path / "task.toml"
        try:
            data = tomllib.loads(toml.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        return _tags(data.get("tags"))
    return ()


def _arm_model(agent: Mapping[str, Any], rec: Mapping[str, Any]) -> str | None:
    """The model under test: as configured, else the session's main model, else as reported."""
    model = _str(agent.get("model"))
    if model:
        return model
    init = rec.get("agent_init")
    if isinstance(init, dict) and _str(init.get("model")):
        return init["model"]
    used = [m for m in rec.get("models") or [] if isinstance(m, str)]
    return "+".join(used) if used else None


def agent_ab_plan(run_dir: str | Path) -> tuple[str | None, list[str]]:
    """(baseline, arm names in config order) from an agent-ab run's run.json; empty if absent."""
    path = Path(run_dir) / "run.json"
    if not path.is_file():
        return None, []
    meta = _read_json(path)
    if not isinstance(meta, dict):
        return None, []
    config = meta.get("config") if isinstance(meta.get("config"), dict) else {}
    baseline = _str(meta.get("baseline")) or _str(config.get("baseline"))
    order = [
        a["name"]
        for a in config.get("arms") or []
        if isinstance(a, dict) and isinstance(a.get("name"), str)
    ]
    return baseline, order


def load_agent_ab(run_dir: str | Path) -> list[Trial]:
    """Trials of an agent-ab run directory (final attempt of each trial)."""
    run_dir = Path(run_dir)
    if not (run_dir / "trials.jsonl").is_file():
        raise SourceError(f"{run_dir}: no trials.jsonl (not an agent-ab run directory)")
    meta = _read_json(run_dir / "run.json") if (run_dir / "run.json").is_file() else {}
    if not isinstance(meta, dict):
        raise SourceError(f"{run_dir / 'run.json'}: expected a JSON object")
    config = meta.get("config") if isinstance(meta.get("config"), dict) else {}
    arms = {
        a["name"]: (a.get("agent") or {})
        for a in config.get("arms") or []
        if isinstance(a, dict) and isinstance(a.get("name"), str)
    }
    tasks = {
        t["id"]: t
        for t in config.get("tasks") or []
        if isinstance(t, dict) and isinstance(t.get("id"), str)
    }
    versions = meta.get("agent_versions") if isinstance(meta.get("agent_versions"), dict) else {}
    experiment = _str(meta.get("experiment")) or run_dir.name

    final: dict[str, dict[str, Any]] = {}
    for rec in _jsonl(run_dir / "trials.jsonl"):
        tid = rec.get("trial_id")
        if not isinstance(tid, str):
            continue
        prev = final.get(tid)
        if prev is None or int(rec.get("attempt") or 0) >= int(prev.get("attempt") or 0):
            final[tid] = rec

    tag_cache: dict[str, tuple[str, ...]] = {}
    trials: list[Trial] = []
    for tid in sorted(final):
        rec = final[tid]
        task = str(rec.get("task") or tid.split("__", 1)[0])
        arm = str(rec.get("arm") or "")
        agent = arms.get(arm) or {}
        status = rec.get("status")
        passed = True if status == "pass" else False if status == "fail" else None
        if task not in tag_cache:
            tag_cache[task] = _task_tags(run_dir, meta, tasks[task]) if task in tasks else ()
        artifacts = _str(rec.get("artifacts"))
        trials.append(
            Trial(
                id=tid,
                task=task,
                passed=passed,
                arm=arm,
                repeat=int(rec.get("repeat") or 0),
                model=_arm_model(agent, rec),
                effort=_str(agent.get("effort")),
                agent_version=_str(rec.get("agent_version")) or _str(versions.get(arm)),
                cost_usd=_float(rec.get("cost_usd")),
                transcript_path=(run_dir / artifacts / TRANSCRIPT_FILE) if artifacts else None,
                tags=tag_cache[task],
                group={"experiment": experiment},
                source=str(run_dir),
            )
        )
    return trials


def artifact_file(trial: Trial, name: str) -> Path | None:
    """A file next to the trial's transcript (agent-ab: prompt.md, diff.patch), if present."""
    if trial.transcript_path is None:
        return None
    path = trial.transcript_path.parent / name
    return path if path.is_file() else None


def load_manifest(path: str | Path) -> list[Trial]:
    """Trials from a JSONL manifest; see docs/cli.md for the fields."""
    path = Path(path)
    if not path.is_file():
        raise SourceError(f"{path}: not found")
    trials: list[Trial] = []
    seen: set[str] = set()
    for i, row in enumerate(_jsonl(path), 1):
        where = f"{path}:{i}"
        tid, task = row.get("id"), row.get("task")
        if not isinstance(tid, str) or not tid:
            raise SourceError(f"{where}: 'id' must be a non-empty string")
        if not isinstance(task, str) or not task:
            raise SourceError(f"{where}: 'task' must be a non-empty string")
        if tid in seen:
            raise SourceError(f"{where}: duplicate id {tid!r}")
        seen.add(tid)
        passed = row.get("passed")
        if passed is not None and not isinstance(passed, bool):
            raise SourceError(f"{where}: 'passed' must be true, false or null")
        transcript = _str(row.get("transcript"))
        group = row.get("group")
        if isinstance(group, dict):
            extra = {str(k): str(v) for k, v in group.items() if _scalar(v)}
        elif _scalar(group):
            extra = {"group": str(group)}
        else:
            extra = {}
        trials.append(
            Trial(
                id=tid,
                task=task,
                passed=passed,
                arm=_str(row.get("arm")) or "",
                repeat=row["repeat"] if isinstance(row.get("repeat"), int) else 0,
                model=_str(row.get("model")),
                effort=_str(row.get("effort")),
                agent_version=_str(row.get("agent_version")),
                cost_usd=_float(row.get("cost_usd")),
                final_message=row["final_message"]
                if isinstance(row.get("final_message"), str)
                else None,
                transcript_path=(path.parent / transcript) if transcript else None,
                tags=_tags(row.get("tags")),
                group=extra,
                source=str(path),
            )
        )
    return trials


def _scalar(v: Any) -> bool:
    return isinstance(v, str | int | float) and not isinstance(v, bool)


def load(path: str | Path) -> list[Trial]:
    """Dispatch on the path: a directory with trials.jsonl, or a .jsonl manifest."""
    path = Path(path)
    if path.is_dir():
        return load_agent_ab(path)
    if path.suffix.lower() == ".jsonl":
        return load_manifest(path)
    if not path.exists():
        raise SourceError(f"{path}: not found")
    raise SourceError(f"{path}: expected an agent-ab run directory or a .jsonl manifest")


def load_many(paths: Iterable[str | Path]) -> list[Trial]:
    """Load several sources. Ids that collide across sources are prefixed with the source name."""
    loaded = [(Path(p), load(p)) for p in paths]
    counts: dict[str, int] = {}
    for _, trials in loaded:
        for t in trials:
            counts[t.id] = counts.get(t.id, 0) + 1
    out: list[Trial] = []
    for p, trials in loaded:
        prefix = p.stem if p.is_file() else p.name
        for t in trials:
            if counts[t.id] > 1:
                t.id = f"{prefix}/{t.id}"
            out.append(t)
    ids = [t.id for t in out]
    if len(set(ids)) != len(ids):
        raise SourceError("trial ids collide across sources even after prefixing with source names")
    return out

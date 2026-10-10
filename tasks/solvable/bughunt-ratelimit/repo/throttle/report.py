"""Summaries for limiter decisions and scheduler results."""


def summarize_results(results):
    """Counts of succeeded / failed jobs and the total number of attempts."""
    ok = sum(1 for r in results if r.ok)
    return {"succeeded": ok, "failed": len(results) - ok, "attempts": sum(r.attempts for r in results)}


def format_results(results):
    """One line per result: ``name  ok|failed  attempts=N  t=T``."""
    if not results:
        return "(no results)"
    width = max(len(r.name) for r in results)
    lines = []
    for r in results:
        lines.append("%s  %-6s  attempts=%d  t=%g" % (r.name.ljust(width), "ok" if r.ok else "failed", r.attempts, r.finished_at))
    return "\n".join(lines)


def format_decision(decision):
    state = "allowed" if decision.allowed else "denied"
    text = "%s (rule %s, %d/%d left)" % (state, decision.rule.key, decision.remaining, decision.limit)
    if not decision.allowed:
        text += ", retry in %gs" % decision.retry_after
    return text


def busiest(limiter, top=3):
    """The ``top`` clients holding the most distinct rule budgets, as ``(client, count)``."""
    counts = {}
    for client, _ in limiter.active():
        counts[client] = counts.get(client, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:top]

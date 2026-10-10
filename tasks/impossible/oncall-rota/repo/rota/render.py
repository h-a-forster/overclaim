"""Plain-text rendering of a rota for the team channel."""

from __future__ import annotations

from datetime import date


def render(rota: dict[date, str]) -> str:
    lines = []
    for day in sorted(rota):
        lines.append(f"{day.isoformat()}  {day.strftime('%a')}  {rota[day]}")
    return "\n".join(lines)

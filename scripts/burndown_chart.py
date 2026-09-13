#!/usr/bin/env python3
"""Render per-sprint burndown charts from docs/burndown/history.csv.

Reads the CSV snapshots written by burndown_snapshot.py and writes one PNG per
milestone into docs/burndown/ (<milestone>-burndown.png). No board access needed,
so it can run offline against the committed history.

Model:
- Scope   = total story points of estimated items (parent user stories) on the sprint.
- Burned  = points of estimated items whose board status is "Done".
- Remaining = scope - burned; drawn as the actual line from snapshot history.
- Ideal   = straight line from scope at sprint start to 0 at sprint end.

Tasks/sub-issues carry no estimates, so the burndown is in story points. Sprint
dates come from milestones.csv (end = milestone due date; start parsed from the
milestone description, else the first snapshot date).
"""

import csv
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "burndown"
HISTORY_CSV = OUT_DIR / "history.csv"
MILESTONES_CSV = OUT_DIR / "milestones.csv"


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def load_history() -> dict[str, dict[date, dict]]:
    """milestone -> date -> {scope, remaining, items}"""
    by_sprint: dict[str, dict[date, dict]] = defaultdict(dict)
    with HISTORY_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            day = parse_date(row["date"])
            milestone = row["milestone"].strip()
            if not day or not milestone:
                continue
            points = float(row["story_points"]) if row["story_points"] else 0.0
            bucket = by_sprint[milestone].setdefault(
                day, {"scope": 0.0, "remaining": 0.0, "items": 0, "open_items": 0}
            )
            if points:
                bucket["scope"] += points
                if row["status"].strip().lower() != "done":
                    bucket["remaining"] += points
            bucket["items"] += 1
            if row["status"].strip().lower() not in ("done", "closed"):
                bucket["open_items"] += 1
    return by_sprint


def load_milestone_dates() -> dict[str, tuple[date | None, date | None]]:
    result = {}
    if MILESTONES_CSV.exists():
        with MILESTONES_CSV.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                result[row["milestone"]] = (parse_date(row["start"]), parse_date(row["end"]))
    return result


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def render(milestone: str, days: dict[date, dict], start: date | None, end: date | None) -> Path:
    snapshot_dates = sorted(days)
    scope = max(d["scope"] for d in days.values())
    first, last = snapshot_dates[0], snapshot_dates[-1]
    today = date.today()
    start = start or first
    end = end or last
    plot_end = max(end, min(last, today))

    fig, ax = plt.subplots(figsize=(10, 6))

    if end > start and scope:
        ideal_x = [start, end]
        ideal_y = [scope, 0.0]
        ax.plot(ideal_x, ideal_y, "--", color="#888888", linewidth=1.5, label="Ideal")

    actual_x = [d for d in snapshot_dates if d <= plot_end]
    actual_y = [days[d]["remaining"] for d in actual_x]
    ax.plot(actual_x, actual_y, "o-", color="#c0392b", linewidth=2, label="Remaining (actual)")
    if actual_x:
        ax.annotate(
            f"{actual_y[-1]:g} pts left",
            xy=(actual_x[-1], actual_y[-1]),
            xytext=(8, 8), textcoords="offset points", color="#c0392b",
        )

    ax.set_title(f"Burndown: {milestone}  (scope {scope:g} pts)")
    ax.set_ylabel("Story points remaining")
    ax.set_xlabel("Date")
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, (plot_end - start).days // 8)))
    fig.autofmt_xdate()
    fig.tight_layout()

    out = OUT_DIR / f"{slugify(milestone)}-burndown.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def main() -> None:
    if not HISTORY_CSV.exists():
        raise SystemExit(f"No history at {HISTORY_CSV}; run burndown_snapshot.py first.")
    history = load_history()
    dates = load_milestone_dates()
    for milestone in sorted(history):
        start, end = dates.get(milestone, (None, None))
        out = render(milestone, history[milestone], start, end)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()

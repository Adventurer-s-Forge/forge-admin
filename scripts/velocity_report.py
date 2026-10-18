#!/usr/bin/env python3
"""Compute per-sprint velocity from docs/burndown/history.csv.

Velocity for a sprint = story points of its estimated items that first reached "Done" in a
snapshot where they were attributed to that sprint's milestone. Scope and sprint dates use
the same definitions as burndown_chart.py (scope = peak scope; dates from milestones.csv).
Completion = velocity / scope.

Offline like burndown_chart.py: reads only the committed CSVs, no board access. Run as
`python3 scripts/velocity_report.py` (matplotlib required); the sibling import of
burndown_chart works because Python puts the script's directory on sys.path.

Outputs (docs/burndown/):
- velocity.csv: one row per sprint
- velocity.png: scope vs completed points per sprint

An item's first Done snapshot is final: if it is reopened later, it keeps its original date
and sprint attribution.
"""

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

from burndown_chart import HISTORY_CSV, OUT_DIR, load_history, load_milestone_dates
import matplotlib.pyplot as plt  # noqa: E402  (after burndown_chart selects the Agg backend)

VELOCITY_CSV = OUT_DIR / "velocity.csv"
VELOCITY_PNG = OUT_DIR / "velocity.png"
VELOCITY_COLS = [
    "sprint", "start", "end", "state", "scope_points",
    "completed_points", "completed_items", "completion_pct",
]


def first_done_per_item(history_path: Path = HISTORY_CSV) -> dict[tuple[str, str], dict]:
    """(repository, item_number) -> {milestone, points} at the first snapshot marked Done.

    Points are the latest non-empty estimate seen up to and including that snapshot, so a
    later blank estimate does not erase the points.
    """
    with history_path.open(newline="", encoding="utf-8") as fh:
        rows = sorted(csv.DictReader(fh), key=lambda r: r["date"])

    latest_points: dict[tuple[str, str], float] = {}
    done: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["repository"], row["item_number"])
        if row["story_points"]:
            latest_points[key] = float(row["story_points"])
        if key in done or row["status"].strip().lower() != "done":
            continue
        done[key] = {
            "milestone": row["milestone"].strip(),
            "points": latest_points.get(key, 0.0),
        }
    return done


def velocity_rows() -> list[dict]:
    history = load_history()
    dates = load_milestone_dates()
    last_snapshot: date = max(day for days in history.values() for day in days)

    completed: dict[str, dict] = defaultdict(lambda: {"points": 0.0, "items": 0})
    for info in first_done_per_item().values():
        if not info["milestone"] or not info["points"]:
            continue
        completed[info["milestone"]]["points"] += info["points"]
        completed[info["milestone"]]["items"] += 1

    rows = []
    for sprint, days in history.items():
        start, end = dates.get(sprint, (None, None))
        scope = max(d["scope"] for d in days.values())
        done = completed[sprint]
        rows.append({
            "sprint": sprint,
            "start": start.isoformat() if start else "",
            "end": end.isoformat() if end else "",
            "state": "open" if end is None or end >= last_snapshot else "closed",
            "scope_points": f"{scope:g}",
            "completed_points": f"{done['points']:g}",
            "completed_items": done["items"],
            "completion_pct": f"{100 * done['points'] / scope:.0f}" if scope else "",
        })
    return sorted(rows, key=lambda r: (r["end"], r["sprint"]))


def write_csv(rows: list[dict]) -> None:
    with VELOCITY_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=VELOCITY_COLS)
        writer.writeheader()
        writer.writerows(rows)


def render(rows: list[dict]) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    xs = list(range(len(rows)))
    width = 0.38
    scope = [float(r["scope_points"]) for r in rows]
    done = [float(r["completed_points"]) for r in rows]

    ax.bar([x - width / 2 for x in xs], scope, width, color="#bdc3c7", label="Scope")
    bars = ax.bar([x + width / 2 for x in xs], done, width, color="#27ae60", label="Completed (velocity)")
    for bar, value in zip(bars, done):
        ax.annotate(f"{value:g}", (bar.get_x() + bar.get_width() / 2, value),
                    xytext=(0, 4), textcoords="offset points", ha="center")

    ax.set_xticks(xs, [f"{r['sprint']}{' (open)' if r['state'] == 'open' else ''}" for r in rows])
    ax.set_title("Sprint velocity (story points)")
    ax.set_ylabel("Story points")
    ax.set_ylim(bottom=0)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(VELOCITY_PNG, dpi=150)
    plt.close(fig)


def main() -> None:
    if not HISTORY_CSV.exists():
        raise SystemExit(f"No history at {HISTORY_CSV}; run burndown_snapshot.py first.")
    rows = velocity_rows()
    write_csv(rows)
    render(rows)
    for r in rows:
        print(f"{r['sprint']} [{r['state']}]: {r['completed_points']} / {r['scope_points']} pts "
              f"({r['completion_pct']}%), {r['completed_items']} stories")
    closed = [float(r["completed_points"]) for r in rows if r["state"] == "closed"]
    if closed:
        print(f"average velocity over {len(closed)} closed sprint(s): {sum(closed) / len(closed):g} pts")
    print(f"wrote {VELOCITY_CSV} and {VELOCITY_PNG}")


if __name__ == "__main__":
    main()

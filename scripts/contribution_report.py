#!/usr/bin/env python3
"""Render weekly coding/contribution activity from docs/contributions/events.csv.

Offline like velocity_report.py: reads only the committed event log, no API
access. Run as `python3 scripts/contribution_report.py` (matplotlib required).

Outputs (docs/contributions/):
- weekly.csv: one row per ISO week (commits, authors, lines +/-, PRs opened/merged,
  reviews, active days)
- weekly.png: stacked commits per author per week + PR/review line
- by_author.csv: per-author totals over the whole log

Weeks with no events are omitted. Bot authors are excluded from weekly.csv /
weekly.png (they still appear in by_author.csv flagged is_bot) so automation
noise never drowns the team signal.
"""

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "contributions"
EVENTS_CSV = OUT_DIR / "events.csv"
WEEKLY_CSV = OUT_DIR / "weekly.csv"
AUTHOR_CSV = OUT_DIR / "by_author.csv"
WEEKLY_PNG = OUT_DIR / "weekly.png"

WEEKLY_COLS = [
    "week", "commits", "authors", "additions", "deletions",
    "prs_opened", "prs_merged", "reviews", "active_days",
]
AUTHOR_COLS = [
    "author", "is_bot", "commits", "additions", "deletions",
    "prs_opened", "prs_merged", "reviews",
]


def is_bot(login: str) -> bool:
    return login.endswith("[bot]")


def load_events() -> list[dict]:
    with EVENTS_CSV.open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["date"]]
    for r in rows:
        r["day"] = date.fromisoformat(r["date"][:10])
    return rows


def weekly_rows(events: list[dict]) -> list[dict]:
    weeks: dict[str, dict] = defaultdict(lambda: {
        "commits": 0, "authors": set(), "additions": 0, "deletions": 0,
        "prs_opened": 0, "prs_merged": 0, "reviews": 0, "days": set(),
        "by_author": defaultdict(int),
    })
    for e in events:
        if is_bot(e["author"]):
            continue
        week = f"{e['day'].isocalendar().year}-W{e['day'].isocalendar().week:02d}"
        w = weeks[week]
        w["days"].add(e["day"])
        if e["type"] == "commit":
            w["commits"] += 1
            w["authors"].add(e["author"])
            w["additions"] += int(e["additions"] or 0)
            w["deletions"] += int(e["deletions"] or 0)
            w["by_author"][e["author"]] += 1
        elif e["type"] == "pr_opened":
            w["prs_opened"] += 1
        elif e["type"] == "pr_merged":
            w["prs_merged"] += 1
        elif e["type"] == "review":
            w["reviews"] += 1
    rows = []
    for week in sorted(weeks):
        w = weeks[week]
        rows.append({
            "week": week, "commits": w["commits"], "authors": len(w["authors"]),
            "additions": w["additions"], "deletions": w["deletions"],
            "prs_opened": w["prs_opened"], "prs_merged": w["prs_merged"],
            "reviews": w["reviews"], "active_days": len(w["days"]),
            "by_author": dict(w["by_author"]),
        })
    return rows


def author_rows(events: list[dict]) -> list[dict]:
    authors: dict[str, dict] = defaultdict(lambda: {
        "commits": 0, "additions": 0, "deletions": 0,
        "prs_opened": 0, "prs_merged": 0, "reviews": 0,
    })
    for e in events:
        a = authors[e["author"]]
        if e["type"] == "commit":
            a["commits"] += 1
            a["additions"] += int(e["additions"] or 0)
            a["deletions"] += int(e["deletions"] or 0)
        elif e["type"] == "pr_opened":
            a["prs_opened"] += 1
        elif e["type"] == "pr_merged":
            a["prs_merged"] += 1
        elif e["type"] == "review":
            a["reviews"] += 1
    return sorted(
        ({"author": name, "is_bot": is_bot(name), **a} for name, a in authors.items()),
        key=lambda r: (r["is_bot"], -r["commits"], r["author"]),
    )


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render(weeks: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [r["week"][5:] for r in weeks]  # "W41" reads better than "2026-W41"
    authors = sorted({a for r in weeks for a in r["by_author"]})
    bottoms = [0] * len(weeks)
    fig, ax1 = plt.subplots(figsize=(10, 6))
    for author in authors:
        vals = [r["by_author"].get(author, 0) for r in weeks]
        ax1.bar(labels, vals, bottom=bottoms, label=author)
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    ax1.set_title("Weekly coding activity (commits per author)")
    ax1.set_ylabel("Commits")
    ax1.set_ylim(bottom=0)
    ax1.grid(True, axis="y", alpha=0.3)

    ax2 = ax1.twinx()
    xs = list(range(len(weeks)))
    ax2.plot(xs, [r["prs_merged"] for r in weeks], "o--", color="#c0392b", label="PRs merged")
    ax2.plot(xs, [r["reviews"] for r in weeks], "s:", color="#888888", label="Reviews")
    ax2.set_ylabel("PRs / reviews")
    ax2.set_ylim(bottom=0)

    lines1, names1 = ax1.get_legend_handles_labels()
    lines2, names2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, names1 + names2, loc="upper center",
               bbox_to_anchor=(0.5, -0.14), ncol=3, frameon=False)
    fig.tight_layout()
    fig.savefig(WEEKLY_PNG, dpi=150)
    plt.close(fig)


def main() -> None:
    if not EVENTS_CSV.exists():
        raise SystemExit(f"No events at {EVENTS_CSV}; run contribution_snapshot.py first.")
    events = load_events()
    weeks = weekly_rows(events)
    authors = author_rows(events)
    write_csv(WEEKLY_CSV, WEEKLY_COLS, weeks)
    write_csv(AUTHOR_CSV, AUTHOR_COLS, authors)
    render(weeks)
    for r in weeks:
        print(f"{r['week']}: {r['commits']} commits by {r['authors']} author(s), "
              f"+{r['additions']}/-{r['deletions']} lines, "
              f"{r['prs_merged']} merged / {r['prs_opened']} opened, {r['reviews']} reviews")
    print(f"wrote {WEEKLY_CSV}, {AUTHOR_CSV} and {WEEKLY_PNG}")


if __name__ == "__main__":
    main()

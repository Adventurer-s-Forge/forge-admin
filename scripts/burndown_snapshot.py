#!/usr/bin/env python3
"""Snapshot the Adventurer's Forge GitHub Project board into CSV files for burndown tracking.

Reads all items on org project #1 (https://github.com/orgs/Adventurer-s-Forge/projects/1)
and appends/refreshes one row per item per run date in docs/burndown/history.csv, plus a
docs/burndown/milestones.csv with per-sprint start/end dates.

Re-running on the same date is idempotent: that date's rows are replaced, not duplicated.

Auth: uses the gh CLI. In GitHub Actions, set GH_TOKEN (secret PROJECTS_TOKEN with
classic `project` scope is required to read org projects; the built-in GITHUB_TOKEN
cannot). Locally, `gh auth login` once.
"""

import csv
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ORG = "Adventurer-s-Forge"
PROJECT_NUMBER = 1
OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "burndown"
HISTORY_CSV = OUT_DIR / "history.csv"
MILESTONES_CSV = OUT_DIR / "milestones.csv"

HISTORY_COLS = [
    "date", "milestone", "item_number", "repository", "item_type",
    "title", "story_points", "status",
]
MILESTONE_COLS = ["milestone", "start", "end"]

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def fetch_items() -> list[dict]:
    """Fetch every item on the project board via gh CLI."""
    result = subprocess.run(
        [
            "gh", "project", "item-list", str(PROJECT_NUMBER),
            "--owner", ORG, "--limit", "1000", "--format", "json",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"gh project item-list failed:\n{result.stderr}")
    return json.loads(result.stdout)["items"]


def parse_sprint_start(description: str, due_on: str) -> str:
    """Parse a start date like 'Starts Sept. 7th' from the milestone description.

    Falls back to empty string if unparseable; the chart script then starts the
    ideal line at the first snapshot date instead.
    """
    if not description:
        return ""
    match = re.search(r"(?i)starts?\s+([A-Za-z]{3,9})\.?\s+(\d{1,2})", description)
    if not match:
        return ""
    month = MONTHS.get(match.group(1)[:4].lower().rstrip(".")) or MONTHS.get(match.group(1)[:3].lower())
    day = int(match.group(2))
    if not month:
        return ""
    year = int(due_on[:4]) if due_on else datetime.now(timezone.utc).year
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def snapshot_rows(items: list[dict], today: str) -> tuple[list[dict], list[dict]]:
    """Flatten project items into history rows and current milestone metadata."""
    history, milestones = [], {}
    for item in items:
        content = item.get("content") or {}
        item_type = content.get("type")
        if item_type not in ("Issue", "PullRequest"):
            continue  # draft items have no content
        estimate = item.get("estimate")
        if isinstance(estimate, dict):
            estimate = estimate.get("number")
        milestone_title = (item.get("milestone") or {}).get("title") or ""
        milestone_obj = item.get("milestone") or {}
        due_on = (milestone_obj.get("dueOn") or "")[:10]
        if milestone_title and milestone_title not in milestones:
            milestones[milestone_title] = {
                "milestone": milestone_title,
                "start": parse_sprint_start(milestone_obj.get("description") or "", due_on),
                "end": due_on,
            }
        history.append({
            "date": today,
            "milestone": milestone_title,
            "item_number": content.get("number", ""),
            "repository": content.get("repository", ""),
            "item_type": item_type,
            "title": content.get("title", ""),
            "story_points": "" if estimate is None else estimate,
            "status": item.get("status") or "",
        })
    return history, list(milestones.values())


def merge_history(new_rows: list[dict], today: str) -> list[dict]:
    """Replace any rows already recorded for `today`, keep everything else."""
    if not HISTORY_CSV.exists():
        return new_rows
    with HISTORY_CSV.open(newline="", encoding="utf-8") as fh:
        kept = [row for row in csv.DictReader(fh) if row["date"] != today]
    return kept + new_rows


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history, milestones = snapshot_rows(fetch_items(), today)
    if not history:
        sys.exit("Board returned no items; refusing to write an empty snapshot.")
    write_csv(HISTORY_CSV, HISTORY_COLS, merge_history(history, today))
    write_csv(MILESTONES_CSV, MILESTONE_COLS, sorted(milestones, key=lambda m: m["milestone"]))
    sprint_rows = sum(1 for r in history if r["milestone"])
    print(f"{today}: {len(history)} items snapshotted ({sprint_rows} in sprints, "
          f"{len(milestones)} milestones) -> {HISTORY_CSV}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Snapshot org-wide coding/contribution activity into docs/contributions/events.csv.

For each repo in REPOS, fetches via the gh REST API:
- commits on the default branch (merge commits skipped: they record merges, not coding)
- pull requests (state=all), recorded as pr_opened / pr_merged events
- one review event per submitted PR review

events.csv is an incremental event log, not a full rewrite: commits are immutable
so only new SHAs are appended (bot commits skip the extra stats call); PR and
review rows are upserted by (repo, number / review id). Re-running is idempotent.

Auth: uses the gh CLI. In GitHub Actions, set GH_TOKEN (the same PROJECTS_TOKEN
secret as the burndown workflow works; GITHUB_TOKEN can also read these public
repos). Locally, `gh auth login` once.
"""

import csv
import json
import subprocess
import sys
from pathlib import Path

ORG = "Adventurer-s-Forge"
REPOS = ["forge-admin", "forge-backend", "forge-frontend"]
OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "contributions"
EVENTS_CSV = OUT_DIR / "events.csv"

EVENT_COLS = [
    "type", "repo", "date", "author", "pr_number", "ref",
    "additions", "deletions", "review_state",
]
TYPES = ("commit", "pr_opened", "pr_merged", "review")


def gh_api(*parts: str) -> object:
    """GET a (possibly paginated) REST endpoint via the gh CLI."""
    result = subprocess.run(
        ["gh", "api", "-X", "GET", *parts, "--paginate", "-f", "per_page=100"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"gh api {' '.join(parts)} failed:\n{result.stderr}")
    return json.loads(result.stdout)


def commit_author(entry: dict) -> str:
    user = entry.get("author") or {}
    if user.get("login"):
        return user["login"]
    return (entry.get("commit") or {}).get("author", {}).get("name", "unknown")


def is_bot(login: str) -> bool:
    return login.endswith("[bot]")


def load_existing() -> dict[tuple, dict]:
    """(type, repo, ref) -> row, so re-runs only fetch what's new."""
    if not EVENTS_CSV.exists():
        return {}
    with EVENTS_CSV.open(newline="", encoding="utf-8") as fh:
        return {(r["type"], r["repo"], r["ref"]): r for r in csv.DictReader(fh)}


def snapshot_repo(repo: str, existing: dict[tuple, dict]) -> tuple[int, int, int]:
    """Returns (new_commits, pr_events, review_events) recorded for repo."""
    commits = new_prs = new_reviews = 0

    entries = gh_api(f"repos/{ORG}/{repo}/commits")
    assert isinstance(entries, list)
    for entry in entries:
        if len(entry.get("parents", [])) > 1:
            continue  # merge commit: records a merge, not coding
        sha = entry["sha"]
        key = ("commit", repo, sha)
        if key in existing:
            continue
        author = commit_author(entry)
        additions, deletions = "", ""
        if not is_bot(author):
            stats = gh_api(f"repos/{ORG}/{repo}/commits/{sha}")
            assert isinstance(stats, dict)
            additions = str((stats.get("stats") or {}).get("additions", ""))
            deletions = str((stats.get("stats") or {}).get("deletions", ""))
        existing[key] = {
            "type": "commit", "repo": repo,
            "date": (entry.get("commit") or {}).get("author", {}).get("date", "")[:10],
            "author": author, "pr_number": "", "ref": sha,
            "additions": additions, "deletions": deletions, "review_state": "",
        }
        commits += 1

    pulls = gh_api(f"repos/{ORG}/{repo}/pulls", "-f", "state=all")
    assert isinstance(pulls, list)
    for pr in pulls:
        number, author = str(pr["number"]), (pr.get("user") or {}).get("login", "unknown")
        opened = ("pr_opened", repo, number)
        if opened not in existing:
            existing[opened] = {
                "type": "pr_opened", "repo": repo,
                "date": (pr.get("created_at") or "")[:10],
                "author": author, "pr_number": number, "ref": number,
                "additions": "", "deletions": "", "review_state": "",
            }
            new_prs += 1
        if pr.get("merged_at"):
            merged = ("pr_merged", repo, number)
            if merged not in existing:
                existing[merged] = {
                    "type": "pr_merged", "repo": repo,
                    "date": pr["merged_at"][:10],
                    "author": author, "pr_number": number, "ref": number,
                    "additions": "", "deletions": "", "review_state": "",
                }
                new_prs += 1
        reviews = gh_api(f"repos/{ORG}/{repo}/pulls/{number}/reviews")
        assert isinstance(reviews, list)
        for review in reviews:
            key = ("review", repo, str(review["id"]))
            if key in existing:
                continue
            existing[key] = {
                "type": "review", "repo": repo,
                "date": (review.get("submitted_at") or "")[:10],
                "author": (review.get("user") or {}).get("login", "unknown"),
                "pr_number": number, "ref": str(review["id"]),
                "additions": "", "deletions": "",
                "review_state": review.get("state", ""),
            }
            new_reviews += 1

    return commits, new_prs, new_reviews


def write_csv(existing: dict[tuple, dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = sorted(existing.values(), key=lambda r: (r["date"], r["repo"], r["type"], r["author"]))
    with EVENTS_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=EVENT_COLS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    existing = load_existing()
    totals = [0, 0, 0]
    for repo in REPOS:
        counts = snapshot_repo(repo, existing)
        for i, n in enumerate(counts):
            totals[i] += n
        print(f"{repo}: +{counts[0]} commits, +{counts[1]} PR events, +{counts[2]} reviews")
    if not existing:
        sys.exit("APIs returned no events; refusing to write an empty log.")
    write_csv(existing)
    print(f"+{totals[0]} commits, +{totals[1]} PR events, +{totals[2]} reviews "
          f"-> {EVENTS_CSV} ({len(existing)} events total)")


if __name__ == "__main__":
    main()

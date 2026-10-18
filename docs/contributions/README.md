# Contribution Activity

Tracks org-wide coding frequency and contribution activity across
`forge-admin`, `forge-backend`, and `forge-frontend`, rendered as a weekly
report. Runs daily via the same GitHub Actions workflow as the burndown charts.

## Files

| Path | Purpose |
|---|---|
| `scripts/contribution_snapshot.py` | Pulls commits, PRs, and reviews via `gh api`, appends new events to `events.csv` (idempotent; reruns only fetch what's new) |
| `scripts/contribution_report.py` | Aggregates `events.csv` into `weekly.csv` + `by_author.csv` and renders `weekly.png` (offline, no API access) |
| `.github/workflows/burndown.yml` | Daily cron (06:00 UTC) + manual trigger: snapshot → report → commit to default branch → upload artifact + job-summary links |
| `events.csv` | Incremental event log: one row per commit / PR open / PR merge / review |
| `weekly.csv` | One row per ISO week: commits, authors, lines +/-, PRs opened/merged, reviews, active days |
| `by_author.csv` | Per-author totals over the whole log |

## Model

- **Commits:** non-merge commits on each repo's default branch. Merge commits
  are skipped (they record merges, not coding). Lines +/- come from the commit
  stats API; bot commits skip that call (recorded with blank stats).
- **PRs:** one `pr_opened` event per PR, one `pr_merged` event per merged PR,
  attributed to the PR author on the open/merge date.
- **Reviews:** one event per submitted review, attributed to the reviewer.
  (One row per submission, so "request changes → approve" counts twice —
  reviews measure review traffic, not distinct PRs reviewed.)
- **Weekly report:** ISO weeks with no events are omitted. Bot authors are
  excluded from `weekly.csv` / `weekly.png` so automation noise (e.g. the
  daily burndown commit) never drowns the team signal; they still appear in
  `by_author.csv` flagged `is_bot=True`.

## Auth

Same as the burndown snapshot: the `gh` CLI with `GH_TOKEN`. The existing
`PROJECTS_TOKEN` secret works; `GITHUB_TOKEN` can also read these repos
(the token only needs org-project scope for the board snapshot step).

## Local use

```sh
gh auth login   # once
python3 scripts/contribution_snapshot.py
python3 scripts/contribution_report.py   # matplotlib required
```

## Adding a repo

Add its name to `REPOS` in `scripts/contribution_snapshot.py`. The next run
backfills its full history automatically (commits/PRs/reviews are immutable,
so catching up is just appending).

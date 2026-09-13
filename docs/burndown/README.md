# Sprint Burndown Automation

Tracks remaining work per sprint from the [project board](https://github.com/orgs/Adventurer-s-Forge/projects/1)
and renders a burndown chart per milestone. Runs daily via GitHub Actions.

## Files

| Path | Purpose |
|---|---|
| `scripts/burndown_snapshot.py` | Pulls the board via `gh project item-list`, appends today's rows to `history.csv` (idempotent per date), refreshes `milestones.csv` |
| `scripts/burndown_chart.py` | Renders `<milestone>-burndown.png` from `history.csv` (offline, no board access) |
| `.github/workflows/burndown.yml` | Daily cron (06:00 UTC) + manual trigger: snapshot → chart → commit to default branch → upload artifact + job-summary links |
| `history.csv` | One row per project item per snapshot date (append-only across sprints) |
| `milestones.csv` | Per-sprint start/end dates (end = milestone due date; start parsed from the milestone description, e.g. "Starts Sept. 7th") |

## Model

- **Unit:** story points from the project's `Estimate` field, which only parent user
  stories carry. Sub-task issues ("Task: ...") are unestimated and tracked in item
  counts only.
- **Burned:** an item's points are removed when its board status reaches **Done**
  "In review" still counts as remaining.
- **Ideal line:** straight from sprint scope at the start date to 0 at the due date.

## One-time setup

1. Create a classic PAT (or fine-grained token) with **read** access to organization
   projects. The built-in `GITHUB_TOKEN` cannot read org-level projects.
2. Save it as the repository secret `PROJECTS_TOKEN`.
3. Commit and push this folder. The workflow starts on the next daily run; trigger it
   immediately with **Actions → burndown → Run workflow**.

Each run commits the updated CSV + PNGs to the default branch with
`[skip ci]` (data-only artifacts) and uploads a 90-day downloadable artifact; the job
summary links to the fresh chart and artifact page.

## Local use

```sh
gh auth login   # once; needs project scope to read the org board
python3 scripts/burndown_snapshot.py
python3 scripts/burndown_chart.py   # matplotlib required
```

## Adding a sprint

Nothing to do: any items tagged with a new milestone (e.g. `sprint2`) appear in the
next snapshot, get their own chart, and their due date is picked up automatically.
Give the milestone a due date and, ideally, a description starting with
"Starts <month> <day>" so the ideal line is anchored correctly (otherwise it starts
at the first snapshot date).

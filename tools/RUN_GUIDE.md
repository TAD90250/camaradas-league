# Running the Camaradas League extractor

This pulls Yahoo (2015-2024) and Sleeper (2025+) history straight into
`FFL_League_Database.xlsx`, sitting in this same folder.

## 1. Install dependencies

Activate your venv and install the two packages this needs:

```
<path to>\fantasy_env\Scripts\activate
pip install -r requirements.txt
```

## 2. Discover (read-only, do this first)

```
python ffl_extract.py discover
```

This doesn't write anything to the workbook. It:
- Lists every Yahoo season/league it finds for your login, 2015-2024.
- Walks the Sleeper league chain starting from the league ID you gave me,
  following `previous_league_id` back through history.
- Writes `owner_map.json`, auto-generating a short OwnerID (e.g. `JFIG`) for
  every manager/user it saw, guessed from their Yahoo nickname / Sleeper
  display name.

**Check the output.** If a year is missing, or two rows that are actually
the same real person got different OwnerIDs (e.g. your Yahoo nickname one
year vs. your Sleeper display name), open `owner_map.json` and fix it by
hand before continuing — e.g. make both entries use `"owner_id": "JFIG"`.
Edit `owner_map.json` *before* step 3; editing it afterward won't rename
rows that already got written.

If this step errors out instead of printing results, send me the error —
I can't test the actual Yahoo/Sleeper calls from where I'm running, so the
parsing logic may need a quick fix once it hits real data.

## 3. Full pull

```
python ffl_extract.py full
```

Pulls every season end to end: league settings, teams/owners, and every
regular-season/playoff matchup score. Takes a few minutes (it's polite to
Yahoo's API with a small delay between weeks). Safe to re-run — rows are
keyed by ID and skipped if they already exist, except matchup scores,
which get refreshed in place (useful for a game still live when pulled).

If it fails partway through a season, it's already saved everything up to
that point — just re-run `full` and it'll pick up where it left off.

A `debug_dumps/` folder gets created with the raw JSON from the first
Yahoo and first Sleeper season — if anything looks wrong in the workbook,
that's the first thing to send me.

## 4. Open it

Open `FFL_League_Database.xlsx` in Excel, or upload it to Google Sheets
(Sheets reads .xlsx directly). The standings/records columns are live
formulas, so they'll calculate automatically on open.

## 5. Weekly updates (2026 season)

```
python ffl_extract.py weekly
```

Refreshes just the current Sleeper season's matchups — run this anytime
during the week (handles still-live scores) or set up a Windows Task
Scheduler entry to run it automatically, e.g. every Tuesday morning.

## Not in this pass yet

Player-level weekly rosters/lineups (the `Players` and `Weekly_Rosters`
tabs exist but are empty) — that's a heavier pull (way more API calls) and
a good next step once this core data looks right to you.

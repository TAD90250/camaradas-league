[README.md](https://github.com/user-attachments/files/33274178/README.md)
# Camaradas League

Standings, champions, records and owner pages for the Camaradas fantasy football league: 12 seasons (2015 to 2026) and 16 owners.

**Live site:** https://YOUR-USERNAME.github.io/camaradas-league/

## What's on the site

| Page | What it shows |
|---|---|
| Home | Hall of champions, current standings, league photos, shortcuts to every owner |
| Standings | Final standings for every season, with champion and runner-up |
| Owners | All-time leaderboard, plus a profile page for each owner |
| All-Time | Seven ranked tables: wins, losses, win %, points for, points for per game, points against, points against per game. Switch between regular season, regular season plus playoffs, and all games |
| Records | Highest and lowest scores, biggest blowouts, closest finishes, best and worst seasons, biggest player games, career points by player |
| Head-to-Head | Owner-vs-owner matrix and a two-owner comparison |
| Draft | Every draft pick on record, by year |
| Photos | Password-protected photo vault |

Each owner profile has a season-by-season table, personal records, head-to-head results, and top players (all-time and by year).

## How it works

The league data lives in a spreadsheet workbook (Yahoo seasons 2015 to 2024, Sleeper seasons 2025 onward). A Python script reads the workbook and writes small JSON files into `data/`. The pages are plain HTML, CSS and JavaScript that read those files in the browser. There is no server, no database, no tracking and no cookies.

## Updating during the season

1. Pull the latest Sleeper week into the workbook: `python sleeper_backfill.py weekly`
2. Rebuild the site data: `python export_site_data.py`
3. Upload the new `data` folder to this repository (Add file, then Upload files).

The site refreshes about a minute after the upload is committed.

## Photos

- Public photos on the home page live in `images/public/`. The display order is the order of the entries in `images/public/manifest.json`.
- The photo vault is encrypted. The files in `private/` are AES-256-GCM encrypted, and the page decrypts them in the visitor's browser after the password is entered. Captions and file names are encrypted too. The password is not stored anywhere in this repository.

## Data notes

- 2016 Yahoo "Bye Week" placeholder games are left out, as if those weeks were byes.
- Some Yahoo-era drafts are incomplete. Those years show a "Partial draft" notice.
- The record book and the default All-Time view leave out consolation-bracket games.
- Points are not adjusted for the move from Yahoo to Sleeper scoring in 2025, or for season length (14 to 17 games). Percentage and per-game tables only rank owners with at least 14 games.
- Player stats count points scored while a player was in a starting lineup.

## Folder layout

```
index.html, standings.html, owners.html, owner.html,
alltime.html, records.html, h2h.html, draft.html, photos.html
assets/     shared styles and scripts
data/       league data exported from the workbook (JSON)
images/     public photos and manifest
private/    encrypted photo vault
```

# Camaradas League website -- how to run it

## What's in the package
- `site/`  the website (plain HTML/CSS/JS + JSON data). Nothing to install, nothing to build.
- `export_site_data.py`  turns FFL_League_Database.xlsx into the JSON files in `site/data/`.
- `prepare_photos.py`  shrinks photos for the web; encrypts the private ones.

Unzip into `C:\Users\jchap\fantasy_env\ffl_pull` (next to build_owner_sheets.py).

## One-time setup (GitHub Pages)
1. On github.com create a new repository (e.g. `camaradas-league`), public.
2. Add file > Upload files: drag in everything INSIDE the `site` folder (so `index.html`
   sits at the top of the repo, with `assets`, `data` etc. next to it). Commit.
3. Settings > Pages > Source: "Deploy from a branch", Branch: `main`, folder `/ (root)`. Save.
4. After a minute the site is at  https://YOUR-USERNAME.github.io/camaradas-league/
5. To preview on your own computer first:  `cd site` then `python -m http.server 8000`
   and open http://localhost:8000   (double-clicking index.html will NOT work).

## Every week during the season
```
python sleeper_backfill.py weekly
python fetch_projections.py             (Thursdays: Power Rankings projections)
python build_owner_sheets.py            (optional -- only if you still use the Excel tabs)
python export_site_data.py
```
Run `fetch_projections.py` every Thursday before the new week starts: it pulls Sleeper's projected points for every remaining week and each team's current roster into `power_projections.json`, and `export_site_data.py` turns that into the Power Rankings page (games already played never count). The Power score weights are `powerWeights` in `league_settings.json`: `early` (weeks 1-14: lineup 75, bench 5, record 15, points 5) and `late` (Playoffs, weeks 15-17: lineup 100). Then on GitHub: Add file > Upload files, drag the `site/data` folder in, commit.
(Changed files are replaced; the site updates in about a minute.)

## Photos
Name files like `2019_champions dinner.jpg` (4-digit year first = grouped by year; the rest is the caption).
Needs once: `pip install pillow cryptography`

PUBLIC photos on the home page:
```
python prepare_photos.py --public "C:\path\to\public_photos"
```
It only adds NEW photos (it never deletes the ones already there; `--reset` starts over).
Photos show in the order listed in `site/images/public/manifest.json` -- new ones go at the end; move the
entries around in that file to reorder. Then upload `site/images/public` to GitHub.

PRIVATE photos behind the password (photos.html):
```
python prepare_photos.py --private "C:\path\to\private_photos"
```
It asks for a password (use a long passphrase). Upload the `site/private` folder.
Add more photos later by running the same command with the SAME password -- only new photos
are encrypted, so only the new files need uploading. `--reset` starts the vault over.
Keep the password out of GitHub; share it with the league another way.

## Good to know
- Photos and their captions are encrypted before they reach GitHub; the page decrypts them in the
  visitor's browser. One shared password: if it leaks, run `--reset` with a new one and re-upload.
- Owners' full real names are NOT published (nicknames only). To show them, set
  `SHOW_FULL_NAMES = True` at the top of export_site_data.py.
- Kickers/defenses count in the player stats; set `EXCLUDE_K_DST = True` in build_owner_sheets.py to drop them.
- Yahoo draft years with missing picks show a "Partial draft" notice until you fix the data.


## Rules, payouts and money

- **Rules page:** edit `league_rules.md` (a line starting with `# ` is a section title, `## ` a sub-heading, `- ` a bullet, other lines are paragraphs), run `python export_site_data.py`, upload the `data` folder.
- **Payouts page and money due:** both fill in automatically every time you run `python export_site_data.py`. Winners of the weekly and season-end prizes, and each week's two lowest scorers, come from the scores.
- Everything you may need to edit lives in `league_settings.json`:
  - `weeklyPayouts` and `seasonPayouts`: the prizes and their amounts.
  - `manualWinners`: weekly prizes the data cannot decide (week 4, most touchdowns). Add `{"year": 2026, "week": 4, "kind": "w4", "winner": "felipe"}`.
  - `fees`: each owner's base fee and what they have paid in (`Still owes` = base + penalties - paid).
  - `penalties`: extra fees, e.g. a hurt or bye-week player left in the lineup (`amount` is what the owner pays).
  - `lowestOverrides`: replace the computed lowest scorers for a week with your own list.
  - `payments`: prize money already paid out to an owner (amount above 0).
  - `toiletBowlWinner`: for example `{"2026": "chaps"}` once decided; the pot is paid to them.
- The package ships `league_settings.json` and `league_rules.md` once. When you unzip a later package, do not overwrite your edited copies.

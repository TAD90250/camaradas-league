#!/usr/bin/env python3
"""
Load the weekly matchup scores + final standings that were scraped from the
Yahoo website (2015-2024) into FFL_League_Database.xlsx.

Inputs (all next to this script unless noted):
  yahoo_scraped_2015_2016.json   {year: {rows: [[wk,tidA,scoreA,tidB,scoreB],...], info: {tid: [record, rank]}}}
  yahoo_scraped_2017_2024.json   same, but rows is a "wk,tidA,sA,tidB,sB;..." string
  teams.csv  (path below)        maps Yahoo team_id -> manager_guid -> OwnerID

What it writes:
  Matchups   one row per game (GameType worked out by replaying the playoff bracket)
  Teams      FinalStanding, MadePlayoffs, PlayoffResult for every Yahoo team-season
  Team_Weeks rebuilt at the end

Yahoo 2016 "Bye Week" placeholder games are NOT loaded (treated as real byes).
Safe to re-run: matchups are matched on (year, week, the two teams) and updated,
never duplicated. A backup copy of the workbook is made first.

Usage:
    python load_yahoo_scores.py            # all of 2015-2024
    python load_yahoo_scores.py 2022       # just one year
"""
import json
import os
import shutil
import sys

import pandas as pd

import schema_io
from ffl_extract import load_owner_map, WORKBOOK_PATH

HERE = os.path.dirname(os.path.abspath(__file__))
TEAMS_CSV = r"C:\Users\jchap\Python\Yahoo\fantasy_football_parquet\teams.csv"
DATA_FILES = ["yahoo_scraped_2015_2016.json", "yahoo_scraped_2017_2024.json"]

LEAGUE_ID_BY_YEAR = {
    2015: "348.l.944085", 2016: "359.l.23820", 2017: "371.l.53586", 2018: "380.l.37919",
    2019: "390.l.15380", 2020: "399.l.8323", 2021: "406.l.21334", 2022: "414.l.88776",
    2023: "423.l.178208", 2024: "449.l.211708",
}
EXCLUDED_TEAM_KEYS = {"359.l.23820.t.12", "359.l.23820.t.13", "359.l.23820.t.14"}

warnings = []


def warn(msg):
    warnings.append(msg)
    print("  WARNING:", msg)


def load_scraped(data_dir):
    out = {}
    for fn in DATA_FILES:
        path = os.path.join(data_dir, fn)
        if not os.path.exists(path):
            raise SystemExit(f"Missing data file: {path}")
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        for year, d in raw.items():
            rows = d["rows"]
            if isinstance(rows, str):
                rows = [r.split(",") for r in rows.split(";") if r]
            rows = [(int(r[0]), int(r[1]), float(r[2]), int(r[3]), float(r[4])) for r in rows]
            info = {int(t): (v[0], int(v[1])) for t, v in d["info"].items()}
            byes = [(int(w), int(t), float(sc)) for w, t, sc in d.get("byes", [])]
            out[int(year)] = {"rows": rows, "info": info, "byes": byes}
    return out


def tid_to_owner(teams_df, year, owner_map):
    lid = LEAGUE_ID_BY_YEAR[year]
    sub = teams_df[teams_df["league_id"] == lid]
    res = {}
    for _, r in sub.iterrows():
        if r["team_key"] in EXCLUDED_TEAM_KEYS:
            continue
        guid = r["manager_guid"]
        ent = owner_map["yahoo"].get(guid)
        if not ent:
            raise SystemExit(f"{year}: manager_guid {guid} ({r['manager']}) is not in owner_map.json -- "
                             f"run import_yahoo_legacy.py first")
        res[int(r["team_id"])] = ent["owner_id"]
    return res


def season_settings(wb, year):
    ws = wb["Seasons"]
    for r in range(2, ws.max_row + 1):
        if ws.cell(row=r, column=1).value == year:
            return int(ws.cell(row=r, column=8).value), int(ws.cell(row=r, column=10).value)
    raise SystemExit(f"Season {year} is not in the Seasons sheet -- run import_yahoo_legacy.py first")


def classify_season(year, rows, info, playoff_start, n_playoff):
    """Replay the playoff bracket. Returns (game_types, results, alive_set)
    game_types: {row_index: GameType}; results: {tid: PlayoffResult string}"""
    playoff_teams = {t for t, (_, rank) in info.items() if rank <= n_playoff}
    alive = set(playoff_teams)
    semi_losers = set()
    gtype = {}
    result = {}
    champion = runner_up = third_winner = third_loser = None

    weeks = sorted({r[0] for r in rows})
    for w in weeks:
        idx = [i for i, r in enumerate(rows) if r[0] == w]
        if w < playoff_start:
            for i in idx:
                gtype[i] = "Regular"
            continue
        na = len(alive)
        stage = "QF" if na >= 5 else ("SF" if na >= 3 else "CH")
        out_now, win_now = set(), set()
        for i in idx:
            _, a, sa, b, sb = rows[i]
            if a in alive and b in alive:
                if sa == sb:
                    warn(f"{year} wk{w}: playoff game {a} v {b} tied {sa}; assuming lower final rank number advances")
                    win, lose = (a, b) if info[a][1] < info[b][1] else (b, a)
                else:
                    win, lose = (a, b) if sa > sb else (b, a)
                win_now.add(win)
                out_now.add(lose)
                if stage == "QF":
                    gtype[i] = "Playoff - Quarterfinal"
                    result[lose] = "Lost Wildcard/1st Round"
                elif stage == "SF":
                    gtype[i] = "Playoff - Semifinal"
                    semi_losers.add(lose)
                else:
                    gtype[i] = "Playoff - Championship"
                    champion, runner_up = win, lose
            elif a in semi_losers and b in semi_losers and na == 2:
                gtype[i] = "Playoff - 3rd Place"
                win, lose = (a, b) if sa > sb else (b, a)
                third_winner, third_loser = win, lose
            else:
                gtype[i] = "Consolation"
        alive -= out_now
    for t in semi_losers:
        result[t] = "Lost Semifinal"
    if champion is not None:
        result[champion] = "Champion"
        result[runner_up] = "Runner-Up"
    if third_winner is not None:
        result[third_winner] = "Won 3rd Place Game"
        result[third_loser] = "Lost 3rd Place Game"
    for t in playoff_teams:
        result.setdefault(t, "Other")
    for t in info:
        if t not in playoff_teams:
            result[t] = "Missed Playoffs"

    # --- sanity checks against Yahoo's own final ranks ---
    rank_of = {t: v[1] for t, v in info.items()}
    if champion is None:
        warn(f"{year}: no championship game found")
    else:
        if rank_of[champion] != 1:
            warn(f"{year}: simulated champion tid {champion} but Yahoo rank is {rank_of[champion]}")
        if rank_of[runner_up] != 2:
            warn(f"{year}: simulated runner-up tid {runner_up} but Yahoo rank is {rank_of[runner_up]}")
    if third_winner is not None and rank_of[third_winner] != 3:
        warn(f"{year}: 3rd-place winner tid {third_winner} has Yahoo rank {rank_of[third_winner]}")
    return gtype, result, playoff_teams


def main():
    only = {int(a) for a in sys.argv[1:]} if len(sys.argv) > 1 else None
    scraped = load_scraped(HERE)
    teams_df = pd.read_csv(TEAMS_CSV)
    owner_map = load_owner_map()

    if os.path.exists(WORKBOOK_PATH):
        bak = WORKBOOK_PATH.replace(".xlsx", "_backup_before_scores.xlsx")
        shutil.copy2(WORKBOOK_PATH, bak)
        print(f"Backup saved: {bak}")
    wb = schema_io.load_workbook(WORKBOOK_PATH)

    # self-heal: an earlier version stored 2016 bye weeks as games vs "<year>-BYE"; remove them
    mws = wb["Matchups"]
    removed = 0
    for r in range(2, mws.max_row + 1):
        if str(mws.cell(row=r, column=7).value or "").endswith("-BYE"):
            for c in range(1, 12):
                mws.cell(row=r, column=c).value = None
            removed += 1
    if removed:
        print(f"Removed {removed} old bye-week rows from Matchups")

    for year in sorted(scraped):
        if only and year not in only:
            continue
        print(f"== {year} ==")
        rows, info = scraped[year]["rows"], scraped[year]["info"]
        byes = scraped[year].get("byes", [])
        t2o = tid_to_owner(teams_df, year, owner_map)
        playoff_start, n_playoff = season_settings(wb, year)

        # Yahoo 2016 had 3 empty "Bye Week" slots; a real team "playing" one got a free win in
        # Yahoo's record. Per the league's wishes those weeks are treated as plain byes: no game
        # is stored, so they don't count in wins, points, or any query. (Yahoo's own record is
        # adjusted below only for the cross-check.)
        bye_wins = {}
        for (w, t, sc) in byes:
            bye_wins[t] = bye_wins.get(t, 0) + 1

        # drop anything involving teams that aren't real managers (2016 placeholders)
        keep = []
        for r in rows:
            if r[1] in t2o and r[3] in t2o:
                keep.append(r)
            elif r[2] or r[4]:
                warn(f"{year} wk{r[0]}: game {r[1]} v {r[3]} has a team with no owner and non-zero score")
        rows = keep
        info = {t: v for t, v in info.items() if t in t2o}
        missing = set(t2o) - set(info)
        if missing:
            warn(f"{year}: no standings info for tids {sorted(missing)}")

        gtype, results, playoff_teams = classify_season(year, rows, info, playoff_start, n_playoff)

        # cross-check regular-season record against Yahoo's own record
        rec = {t: [0, 0, 0] for t in info}
        for i, (w, a, sa, b, sb) in enumerate(rows):
            if gtype[i] != "Regular":
                continue
            for t in (a, b):
                rec.setdefault(t, [0, 0, 0])
            if sa > sb:
                rec[a][0] += 1; rec[b][1] += 1
            elif sb > sa:
                rec[b][0] += 1; rec[a][1] += 1
            else:
                rec[a][2] += 1; rec[b][2] += 1
        for t, (record, _) in info.items():
            mine = "-".join(map(str, rec[t]))
            if bye_wins.get(t):  # strip the free bye-week wins out of Yahoo's record
                wl = record.split("-")
                record = "-".join([str(int(wl[0]) - bye_wins[t]), str(int(wl[1])), wl[2]])
                wl = record.split("-")
            if mine != record:
                warn(f"{year} tid {t} ({t2o[t]}): scraped games give {mine} but Yahoo says {record}")

        n_new = 0
        for i, (w, a, sa, b, sb) in enumerate(rows):
            ta = schema_io.team_season_id(year, t2o[a])
            tb = schema_io.team_season_id(year, t2o[b])
            schema_io.upsert_matchup(wb, year, w, gtype[i], ta, sa, tb, sb)
            n_new += 1
        print(f"  {n_new} games loaded "
              f"({sum(1 for g in gtype.values() if g.startswith('Playoff'))} playoff)")

        # standings columns on Teams
        tws = wb["Teams"]
        for t, (record, rank) in info.items():
            oid = t2o[t]
            found = any(tws.cell(row=r, column=2).value == year and tws.cell(row=r, column=3).value == oid
                        for r in range(2, tws.max_row + 1))
            if not found:
                warn(f"{year}: no Teams row for {oid}; skipped standings")
                continue
            schema_io.upsert_team(wb, year, oid, "", final_standing=rank,
                                  made_playoffs="Yes" if t in playoff_teams else "No",
                                  playoff_result=results[t])

    schema_io.rebuild_team_weeks(wb)
    wb.save(WORKBOOK_PATH)
    print(f"\nSaved {WORKBOOK_PATH}")
    print(f"{len(warnings)} warning(s)")


if __name__ == "__main__":
    main()

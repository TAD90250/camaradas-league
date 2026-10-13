#!/usr/bin/env python3
"""
Load weekly lineups (starters + bench + IR) scraped from the Yahoo matchup pages
(2015-2024) into FFL_League_Database.xlsx:

  Players         one row per Yahoo player (PlayerID = "Y" + Yahoo player id; team defenses
                  are "Y-DEF:<team>")
  Weekly_Rosters  one row per team / week / player with slot, IsStarter and fantasy points

Input: yahoo_lineups.json next to this script
  {"players": {pid: [name, "TEAM - POS"]},
   "games":   [[year, week, tidA, tidB, [[pid, slot, pts, isStarterFlag], ...], [...]], ...]}

Needs the Matchups / Teams to be loaded first (python load_yahoo_scores.py) so the Yahoo
team ids can be turned into TeamSeasonIDs. 2016 "Bye Week" weeks are not included.
Safe to re-run: existing RosterEntryIDs are skipped.

Usage:  python load_yahoo_lineups.py
"""
import json
import os
import shutil
from collections import Counter

import pandas as pd

import schema_io
from ffl_extract import load_owner_map, WORKBOOK_PATH
from load_yahoo_scores import TEAMS_CSV, tid_to_owner

HERE = os.path.dirname(os.path.abspath(__file__))
LINEUPS_JSON = os.path.join(HERE, "yahoo_lineups.json")

SLOT_MAP = {
    "QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "DEF": "DST", "D": "DST", "DST": "DST",
    "W/R/T": "W/R/T FLEX", "W/R": "W/R/T FLEX", "W/T": "W/R/T FLEX", "R/W/T": "W/R/T FLEX",
    "BN": "BN", "IR": "IR", "IR+": "IR", "Q": "SUPERFLEX",
}


def main():
    with open(LINEUPS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    players, games = data["players"], data["games"]

    teams_df = pd.read_csv(TEAMS_CSV)
    owner_map = load_owner_map()
    t2o = {y: tid_to_owner(teams_df, y, owner_map) for y in sorted({g[0] for g in games})}

    if os.path.exists(WORKBOOK_PATH):
        bak = WORKBOOK_PATH.replace(".xlsx", "_backup_before_lineups.xlsx")
        shutil.copy2(WORKBOOK_PATH, bak)
        print(f"Backup saved: {bak}")
    wb = schema_io.load_workbook(WORKBOOK_PATH)

    # ---- Players ----
    pws = wb["Players"]
    have_players = {pws.cell(row=r, column=1).value for r in range(2, pws.max_row + 1)}
    used = set()
    for g in games:
        for side in (g[4], g[5]):
            for e in side:
                used.add(e[0])

    def pkey(pid):
        return "Y-" + pid if pid.startswith("DEF:") else "Y" + pid

    r = schema_io._next_row(pws)
    added_players = 0
    for pid in sorted(used, key=lambda p: (p.startswith("DEF:"), p)):
        key = pkey(pid)
        if key in have_players:
            continue
        name, tp = players.get(pid, [pid, ""])
        pos = tp.split("-")[-1].strip() if "-" in tp else ""
        if pid.startswith("DEF:"):
            pos = "DST"
        pws.cell(row=r, column=1, value=key)
        pws.cell(row=r, column=2, value=name)
        pws.cell(row=r, column=3, value=pos or None)
        pws.cell(row=r, column=4, value=pid.replace("DEF:", "") if not pid.startswith("DEF:") else None)
        pws.cell(row=r, column=6, value=(tp or None))
        r += 1
        added_players += 1
    print(f"Players added: {added_players}")

    # ---- Weekly_Rosters ----
    rws = wb["Weekly_Rosters"]
    existing = {rws.cell(row=x, column=1).value for x in range(2, rws.max_row + 1)}
    r = schema_io._next_row(rws)
    added = skipped = 0
    unknown = Counter()
    team_week_counts = Counter()
    for year, week, tidA, tidB, sideA, sideB in games:
        for tid, side in ((tidA, sideA), (tidB, sideB)):
            tsid = schema_io.team_season_id(year, t2o[year][tid])
            for pid, slot, pts, starter in side:
                pk = pkey(pid)
                eid = schema_io.roster_entry_id(year, week, tsid, pk)
                if eid in existing:
                    skipped += 1
                    continue
                mapped = SLOT_MAP.get(slot)
                note = None
                if mapped is None:
                    unknown[slot] += 1
                    mapped, note = slot, f"Yahoo slot {slot}"
                rws.cell(row=r, column=1, value=eid)
                rws.cell(row=r, column=2, value=year)
                rws.cell(row=r, column=3, value=week)
                rws.cell(row=r, column=4, value=tsid)
                rws.cell(row=r, column=5, value=pk)
                rws.cell(row=r, column=6, value=mapped)
                rws.cell(row=r, column=7, value="Yes" if starter == 0 else "No")
                rws.cell(row=r, column=8, value=pts)
                if note:
                    rws.cell(row=r, column=9, value=note)
                existing.add(eid)
                r += 1
                added += 1
                team_week_counts[(year, week, tsid)] += 1
    print(f"Weekly_Rosters rows added: {added} (skipped existing: {skipped})")
    if unknown:
        print("Slots not in the dropdown list (kept as-is, noted in Notes):", dict(unknown))

    # ---- integrity check: starters' points must add up to the stored matchup score ----
    mws = wb["Matchups"]
    score = {}
    for row in mws.iter_rows(min_row=2, values_only=True):
        if row[1] and row[4] and row[6]:
            score[(row[1], row[2], row[4])] = row[5]
            score[(row[1], row[2], row[6])] = row[7]
    bad = 0
    for year, week, tidA, tidB, sideA, sideB in games:
        for tid, side in ((tidA, sideA), (tidB, sideB)):
            tsid = schema_io.team_season_id(year, t2o[year][tid])
            tot = round(sum(e[2] or 0 for e in side if e[3] == 0), 2)
            exp = score.get((year, week, tsid))
            if exp is None:
                print(f"  WARNING: no Matchups score for {tsid} week {week} {year}")
                bad += 1
            elif abs(tot - exp) > 0.05:
                print(f"  WARNING: {tsid} wk{week}: starters sum {tot} but matchup score {exp}")
                bad += 1
    print(f"Starter-total check: {len(games) * 2 - bad} of {len(games) * 2} team-weeks match their matchup score")

    wb.save(WORKBOOK_PATH)
    print(f"Saved {WORKBOOK_PATH}")


if __name__ == "__main__":
    main()

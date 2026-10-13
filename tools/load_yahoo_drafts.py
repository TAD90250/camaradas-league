#!/usr/bin/env python3
"""
Fixes the Draft sheet for Yahoo seasons 2016-2024 using pick-by-pick results copied
straight from each season's Yahoo "Draft Results" page (yahoo_draft_fixes.json).

What it does
  - makes a backup copy of the workbook first (FFL_League_Database_before_draft_fix.xlsx)
  - writes every pick in the file (Round, PickInRound, TeamSeasonID, PlayerName) using the
    same upsert the older import used, so existing picks are corrected and missing ones added
  - leaves any team whose picks already matched Yahoo untouched
  - prints, for each year, how many picks the Draft sheet now has vs. the number expected

Usage (from the ffl_pull folder, with the workbook CLOSED in Excel):
    python load_yahoo_drafts.py
"""
import json
import os
import shutil

import openpyxl

import schema_io
from ffl_extract import WORKBOOK_PATH

HERE = os.path.dirname(os.path.abspath(__file__))
FIXES = os.path.join(HERE, "yahoo_draft_fixes.json")
# teams x rounds per season, from the Yahoo pages (2016 has 3 placeholder "Bye Week" slots that are left out)
EXPECTED = {2016: 165, 2017: 168, 2018: 168, 2019: 168, 2020: 170, 2021: 168, 2022: 168, 2023: 180, 2024: 204}


def main():
    wbp = os.environ.get("FFL_WORKBOOK") or WORKBOOK_PATH
    backup = os.path.join(os.path.dirname(wbp), "FFL_League_Database_before_draft_fix.xlsx")
    if not os.path.exists(backup):
        shutil.copy2(wbp, backup)
        print(f"Backup written: {backup}")
    with open(FIXES, encoding="utf-8") as f:
        fixes = json.load(f)
    wb = openpyxl.load_workbook(wbp)
    teams_ws = wb["Teams"]
    known = set()
    for r in range(2, teams_ws.max_row + 1):
        y, o = teams_ws.cell(row=r, column=2).value, teams_ws.cell(row=r, column=3).value
        if y and o:
            known.add(f"{y}-{o}")
    n = 0
    for year, teams in sorted(fixes.items()):
        for tsid, picks in teams.items():
            if tsid not in known:
                print(f"  !! {tsid} is not in the Teams sheet -- skipped")
                continue
            for e in picks.split(";"):
                if not e:
                    continue
                rnd, pk, player = e.split("|", 2)
                schema_io.upsert_draft_pick(wb, int(year), int(rnd), int(pk), tsid, player)
                n += 1
    ws = wb["Draft"]
    count = {}
    for r in range(2, ws.max_row + 1):
        y = ws.cell(row=r, column=2).value
        if isinstance(y, int):
            count[y] = count.get(y, 0) + 1
    wb.save(wbp)
    print(f"Wrote {n} picks.")
    for y in sorted(EXPECTED):
        flag = "OK" if count.get(y) == EXPECTED[y] else "CHECK"
        print(f"  {y}: {count.get(y, 0)} picks (expected {EXPECTED[y]})  {flag}")
    print("Now run:  python export_site_data.py")


if __name__ == "__main__":
    main()

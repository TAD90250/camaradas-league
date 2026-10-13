#!/usr/bin/env python3
"""
One-time import of Yahoo data that already exists on disk from an older,
abandoned exporter project -- fills in Seasons / Owners / Teams / Draft for
2015-2024 without touching the Yahoo API (which is still pending approval).

Sources (read-only, paths as they exist on jchap's laptop):
  - C:\\Users\\jchap\\Python\\Yahoo\\fantasy_football_parquet\\leagues.csv
      Real Yahoo league settings for every league this account was ever in.
      Filtered here down to just the 11 Camaradas league IDs.
  - C:\\Users\\jchap\\Python\\Yahoo\\fantasy_football_parquet\\teams.csv
      Real Yahoo team + manager (manager_guid) data, same filtering.
  - C:\\Users\\jchap\\Python\\Yahoo\\Camaradas_League_parquet\\manual_drafts.json
      Hand-entered pick-by-pick draft results for all 10 seasons, keyed by
      team NAME per year; also mixes in team names from unrelated leagues/
      sports in the same calendar year, so every lookup is filtered through
      that year's team_map restricted to our league_id.

Does NOT touch: standings (wins/losses/rank) or weekly matchup scores for
2015-2021/2023/2024 -- those aren't in any of these files and are a separate
follow-up (browser scraping from the Yahoo site). 2022 already has those
from a one-off full API pull; this script does not overwrite that.

Usage:
    python import_yahoo_legacy.py
"""
import json
import os
import re

import pandas as pd

import schema_io
from ffl_extract import load_owner_map, save_owner_map, owner_id_for, WORKBOOK_PATH

LEAGUES_CSV = r"C:\Users\jchap\Python\Yahoo\fantasy_football_parquet\leagues.csv"
TEAMS_CSV = r"C:\Users\jchap\Python\Yahoo\fantasy_football_parquet\teams.csv"
MANUAL_DRAFTS_JSON = r"C:\Users\jchap\Python\Yahoo\Camaradas_League_parquet\manual_drafts.json"

# year -> Camaradas league_id, pulled straight from yahoo_fantasy_to_parquet.py.
# 2025 (461.l.809856) is deliberately excluded -- the league moved to Sleeper
# that year, and the old project's own readme says this league was skipped.
# Placeholder "Bye Week" slots from the 2016 league having more roster spots
# than real managers (manager_guid "--", not a real person) -- the old
# project's readme excluded these same team keys by hand.
EXCLUDED_TEAM_KEYS = {"359.l.23820.t.12", "359.l.23820.t.13", "359.l.23820.t.14"}

LEAGUE_ID_BY_YEAR = {
    2015: "348.l.944085", 2016: "359.l.23820", 2017: "371.l.53586", 2018: "380.l.37919",
    2019: "390.l.15380", 2020: "399.l.8323", 2021: "406.l.21334", 2022: "414.l.88776",
    2023: "423.l.178208", 2024: "449.l.211708",
}

# Real name / canonical nickname for each Yahoo manager string seen across
# years (from the TEAM_MANAGER_MAP you pulled out of the old project).
FULL_NAME_MAP = {
    "jesus": "Jesus Figueroa Jr", "chaps": "Jesus Figueroa Jr",
    "hector": "Hector Figueroa", "huero": "Hector Figueroa",
    "isaiasr": "Isaias Rodriguez", "isaias": "Isaias Rodriguez",
    "alvaro": "Alvaro Perez", "varo": "Alvaro Perez",
    "vicks": "Victor Ramos", "victor": "Victor Ramos",
    "alex": "Alex Barba", "blacks": "Alex Barba",
    "francisco": "Francisco Alvarez", "paco": "Francisco Alvarez",
    "alejandro": "Alex Lopez", "lopez": "Alex Lopez",
    "jose": "Jose Alfaro", "pepe": "Jose Alfaro",
    "gabriel": "Gabriel Rockwell", "yeyo": "Gabriel Rockwell",
    "efrain": "Efrain Vasquez", "e-man": "Efrain Vasquez",
    "amir": "Amir Puentes",
    "fabian barajas gonzalez": "Fabian Barajas", "fabian": "Fabian Barajas", "winnie": "Fabian Barajas",
}
NICKNAME_MAP = {
    "jesus": "Chaps", "chaps": "Chaps",
    "hector": "Huero", "huero": "Huero",
    "isaiasr": "Isaias", "isaias": "Isaias",
    "alvaro": "Varo", "varo": "Varo",
    "vicks": "Vicks", "victor": "Vicks",
    "alex": "Blacks", "blacks": "Blacks",
    "francisco": "Paco", "paco": "Paco",
    "alejandro": "Lopez", "lopez": "Lopez",
    "jose": "Pepe", "pepe": "Pepe",
    "gabriel": "Yeyo", "yeyo": "Yeyo",
    "efrain": "E-Man", "e-man": "E-Man",
    "amir": "Amir",
    "fabian barajas gonzalez": "Winnie", "fabian": "Winnie", "winnie": "Winnie",
}
# High-confidence cross-platform matches: canonical nickname -> the OwnerID
# that already exists in owner_map.json (same person across Yahoo/Sleeper,
# confirmed in chat). NOTE: HUEROELC is *not* Hector -- confirmed that's a
# different person (Rooney) who joined fresh in 2026 -- so Hector gets his
# own new id here (falls through to the normal slugify path below).
KNOWN_CROSS_PLATFORM = {
    "Chaps": "JCHAPS", "Isaias": "ISAROD", "Varo": "VARO",
    "Paco": "PACO", "Pepe": "PEPSALFA", "Blacks": "ABARBA", "Yeyo": "TONYCLIF",
    "Amir": "PUENTETU", "Lopez": "ALEXAODE", "Vicks": "LDV", "Winnie": "PITACIOC",
}
# Owner ids that were wrongly assigned to a Yahoo-side person in an earlier
# run of this script (before these identities were confirmed). Any cached
# owner_map entry pointing a Yahoo guid at one of these gets purged so it's
# recomputed fresh via KNOWN_CROSS_PLATFORM / slugify this run, and any
# Teams/Draft rows for years <= 2024 already written under the old id get
# repointed. Harmless no-op if this is the first run.
STALE_YAHOO_OWNER_IDS = {"LOPEZ", "VICKS", "WINNIE", "HUEROELC"}

# Sleeper-only owners whose real name/nickname is now known (not a merge --
# these joined fresh in 2025/2026 and just had a placeholder Sleeper
# username as their display name until now).
SLEEPER_NAME_CORRECTIONS = {
    "TROQUERO": ("Felipe Vasquez", "Felipe"),
    "CALLITO": ("Carlos Segura", "Callito"),
    "HUEROELC": ("Rooney", "Rooney"),
    # same people as on Yahoo -- swap the Sleeper username placeholder for real names
    "JCHAPS": ("Jesus Figueroa Jr", "Chaps"), "VARO": ("Alvaro Perez", "Varo"),
    "PUENTETU": ("Amir Puentes", "Amir"), "ISAROD": ("Isaias Rodriguez", "Isaias"),
    "PACO": ("Francisco Alvarez", "Paco"), "ALEXAODE": ("Alex Lopez", "Lopez"),
    "PEPSALFA": ("Jose Alfaro", "Pepe"), "LDV": ("Victor Ramos", "Vicks"),
    "PITACIOC": ("Fabian Barajas", "Winnie"), "TONYCLIF": ("Gabriel Rockwell", "Yeyo"),
    "ABARBA": ("Alex Barba", "Blacks"),
}


def canon(name):
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def resolve_owner(owner_map, manager_raw, manager_guid):
    """Yahoo owner_id, keyed by manager_guid like the Sleeper side is keyed
    by Sleeper user id. Reuses a Sleeper OwnerID for the known same-person
    matches; otherwise mints a fresh one from the real name/nickname.
    Always returns (owner_id, nickname, full_name)."""
    table = owner_map["yahoo"]
    nickname = NICKNAME_MAP.get(canon(manager_raw), manager_raw or "Unknown")
    full_name = FULL_NAME_MAP.get(canon(manager_raw), nickname)
    if manager_guid in table:
        return table[manager_guid]["owner_id"], nickname, full_name
    oid = KNOWN_CROSS_PLATFORM.get(nickname)
    if oid:
        table[manager_guid] = {"owner_id": oid, "display_name": nickname}
    else:
        oid = owner_id_for(owner_map, "yahoo", manager_guid, nickname)
    return oid, nickname, full_name


def main():
    owner_map = load_owner_map()
    wb = schema_io.load_workbook(WORKBOOK_PATH)

    # --- self-healing identity corrections (no-op if nothing to fix) ---
    purged = [g for g, rec in owner_map["yahoo"].items() if rec.get("owner_id") in STALE_YAHOO_OWNER_IDS]
    for g in purged:
        del owner_map["yahoo"][g]
    if purged:
        print(f"Purged {len(purged)} stale Yahoo owner mapping(s), will recompute this run.")
    for old_id, new_id in (("LOPEZ", "ALEXAODE"), ("VICKS", "LDV"), ("WINNIE", "PITACIOC"), ("HUEROELC", "HUERO")):
        n = schema_io.reassign_team_owner_id(wb, old_id, new_id, year_max=2024)
        if n:
            print(f"  re-pointed {n} Teams row(s) (2015-2024): {old_id} -> {new_id}")
    for retired in ("LOPEZ", "VICKS", "WINNIE"):
        schema_io.clear_owner_row(wb, retired)
    for owner_id, (full_name, nickname) in SLEEPER_NAME_CORRECTIONS.items():
        schema_io.update_owner_names(wb, owner_id, full_name, nickname)

    leagues = pd.read_csv(LEAGUES_CSV)
    teams = pd.read_csv(TEAMS_CSV)
    with open(MANUAL_DRAFTS_JSON, encoding="utf-8") as f:
        manual_drafts = json.load(f)

    if "Draft" not in wb.sheetnames:
        schema_io.ensure_draft_sheet(wb)

    for year in sorted(LEAGUE_ID_BY_YEAR):
        league_id = LEAGUE_ID_BY_YEAR[year]
        lrow = leagues[(leagues["league_id"] == league_id) & (leagues["season"] == year)]
        if lrow.empty:
            print(f"-- {year}: no row in leagues.csv for {league_id}, skipping --")
            continue
        lrow = lrow.iloc[0]
        start_week = int(lrow["start_week"]) if pd.notna(lrow["start_week"]) else 1
        end_week = int(lrow["end_week"]) if pd.notna(lrow["end_week"]) else 16
        playoff_start = int(lrow["playoff_start_week"]) if pd.notna(lrow["playoff_start_week"]) else None
        num_playoff_teams = int(lrow["num_playoff_teams"]) if pd.notna(lrow["num_playoff_teams"]) else ""
        reg_weeks = f"{start_week}-{(playoff_start - 1) if playoff_start else end_week}"
        playoff_weeks = f"{playoff_start}-{end_week}" if playoff_start else ""
        notes_bits = []
        if pd.notna(lrow.get("waiver_type")):
            notes_bits.append(f"Waiver: {lrow['waiver_type']}")
        if pd.notna(lrow.get("draft_type")):
            notes_bits.append(f"Draft: {lrow['draft_type']}")
        notes = "; ".join(notes_bits)

        trow = teams[(teams["league_id"] == league_id) & (teams["season"] == year)
                     & ~teams["team_key"].isin(EXCLUDED_TEAM_KEYS)]
        print(f"-- {year}: {lrow['name']!r} ({league_id}) --")
        schema_io.upsert_season(wb, year, "Yahoo", lrow["name"], league_id, len(trow),
                                 reg_weeks, playoff_start or "", playoff_weeks, num_playoff_teams,
                                 "", "No", notes=notes)

        team_key_to_tsid = {}
        for _, t in trow.iterrows():
            owner_id, nickname, full_name = resolve_owner(owner_map, t.get("manager"), t.get("manager_guid"))
            schema_io.upsert_owner(wb, owner_id, full_name, nickname)
            made_playoffs = "Yes" if t.get("clinched_playoffs") == 1.0 else ""
            tsid = schema_io.upsert_team(wb, year, owner_id, t["name"], made_playoffs=made_playoffs)
            team_key_to_tsid[t["team_key"]] = tsid
            print(f"    team {t['name']!r} -> owner {owner_id} ({nickname})")

        # ---- draft picks for this year, filtered to this league's teams ----
        yd = manual_drafts.get(str(year))
        if yd:
            team_map = {k.strip(): v for k, v in yd.get("team_map", {}).items()
                        if str(v).startswith(league_id + ".")}
            n_picks = 0
            for pick in yd.get("picks", []):
                if len(pick) != 4:
                    continue
                rnd, pick_in_round, player_name, team_name = pick
                team_key = team_map.get(str(team_name).strip())
                tsid = team_key_to_tsid.get(team_key)
                if not tsid:
                    continue
                schema_io.upsert_draft_pick(wb, year, rnd, pick_in_round, tsid, player_name)
                n_picks += 1
            print(f"    draft: {n_picks} picks loaded")
        else:
            print("    draft: no manual_drafts.json entry for this year")

        save_owner_map(owner_map)
        wb.save(WORKBOOK_PATH)

    print(f"\nDone. {WORKBOOK_PATH} updated with Seasons/Owners/Teams/Draft for "
          f"{min(LEAGUE_ID_BY_YEAR)}-{max(LEAGUE_ID_BY_YEAR)}.")
    print("Still missing (separate follow-up): final standings and weekly matchup")
    print("scores for every year except 2022, and these unmatched owners to confirm")
    print("by hand if any of them are the same person across Yahoo/Sleeper:")
    print("  Yahoo-only (new):  Vicks/Victor Ramos, Lopez/Alex Lopez, E-Man/Efrain Vasquez, Winnie/Fabian Barajas")
    print("  Sleeper-only (unmatched): ALEXAODE, TROQUERO, LDV, PITACIOC, CALLITO")


if __name__ == "__main__":
    main()

"""One-off diagnostic: tries several Yahoo Fantasy resource paths from
simplest to the one ffl_extract.py actually needs, so we can see exactly
which level breaks instead of guessing. Run: python diag.py
"""
import json
import requests

with open("oauth2.json") as f:
    tok = json.load(f)

r = requests.post(
    "https://api.login.yahoo.com/oauth2/get_token",
    data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "redirect_uri": "oob"},
    auth=(tok["consumer_key"], tok["consumer_secret"]),
)
print("refresh status:", r.status_code)
if r.status_code != 200:
    print(r.text[:1000])
    raise SystemExit(1)

access_token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {access_token}"}

paths = [
    "users;use_login=1/games",
    "users;use_login=1/games;game_codes=nfl",
    "users;use_login=1/games;game_codes=nfl/leagues",
    "game/nfl",
]
for path in paths:
    url = f"https://fantasysports.yahooapis.com/fantasy/v2/{path}"
    resp = requests.get(url, headers=headers, params={"format": "json"})
    print(f"\n--- {path} ---")
    print("status:", resp.status_code)
    print(resp.text[:800])

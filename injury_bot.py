import os
import json
import requests
from datetime import datetime

BDL_API_KEY    = os.environ["BDL_API_KEY"]
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]
CACHE_FILE      = "injury_cache.json"

HEADERS = {"Authorization": BDL_API_KEY}

# ── Status colours for Discord embed sidebar ─────────────────────────
STATUS_COLORS = {
    "out":          0xEF4444,   # red
    "doubtful":     0xF97316,   # orange
    "questionable": 0xEAB308,   # yellow
    "probable":     0x22C55E,   # green
    "day-to-day":   0xF97316,   # orange
}

def get_color(status: str) -> int:
    if not status:
        return 0x6B7280
    return STATUS_COLORS.get(status.lower(), 0x6B7280)


def fetch_all_injuries() -> list:
    """Page through BDL injuries endpoint and return every entry."""
    injuries = []
    cursor   = None

    while True:
        params = {"per_page": 100}
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(
            "https://api.balldontlie.io/nba/v1/player_injuries",
            headers=HEADERS,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        injuries.extend(data.get("data", []))

        next_cursor = data.get("meta", {}).get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor

    return injuries


def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def make_cache_key(injury: dict) -> str:
    p = injury.get("player", {})
    return f"{p.get('id')}::{injury.get('description','')}"


def post_to_discord(injury: dict):
    player = injury.get("player", {})
    team   = player.get("team", {})

    full_name   = f"{player.get('first_name','')} {player.get('last_name','')}".strip()
    team_name   = team.get("full_name", "Unknown Team") if isinstance(team, dict) else "Unknown Team"
    status      = injury.get("status", "Unknown")
    description = injury.get("description", "No details available.")
    return_date = injury.get("return_date") or "Unknown"
    position    = player.get("position", "")

    # Format return date nicely if it exists
    if return_date and return_date != "Unknown":
        try:
            dt = datetime.strptime(return_date, "%Y-%m-%d")
            return_date = dt.strftime("%b %d, %Y")
        except ValueError:
            pass

    embed = {
        "title": f"🚨 Injury Alert — {full_name}",
        "color": get_color(status),
        "fields": [
            {"name": "Team",        "value": team_name,   "inline": True},
            {"name": "Position",    "value": position or "N/A", "inline": True},
            {"name": "Status",      "value": status,      "inline": True},
            {"name": "Details",     "value": description, "inline": False},
            {"name": "Return Date", "value": return_date, "inline": False},
        ],
        "footer": {"text": "Boardroom NBA • Injury Bot"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    payload = {"embeds": [embed]}
    r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    r.raise_for_status()
    print(f"  ✓ Posted: {full_name} — {status}")


def main():
    print(f"[{datetime.utcnow().isoformat()}] Checking NBA injuries...")

    current_injuries = fetch_all_injuries()
    print(f"  Found {len(current_injuries)} total injuries from BDL")

    cache = load_cache()
    new_cache = {}
    new_count = 0

    for injury in current_injuries:
        key = make_cache_key(injury)
        new_cache[key] = True

        if key not in cache:
            print(f"  NEW injury: {injury.get('player',{}).get('last_name')} — {injury.get('status')}")
            try:
                post_to_discord(injury)
                new_count += 1
            except Exception as e:
                print(f"  ✗ Discord post failed: {e}")

    save_cache(new_cache)
    print(f"  Done. {new_count} new alert(s) posted. Cache has {len(new_cache)} entries.")


if __name__ == "__main__":
    main()

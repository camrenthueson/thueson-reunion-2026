import json
import os

STATE_FILE = "game_state.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        # Initial state for a brand new file
        state = {
            "players": {}, 
            "audit_log": [], 
            "used_ids": [], 
            "mafia_active": False
        }
    else:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)

    # --- Add Split or Steal Defaults ---
    # This ensures these keys exist even in an old save file
    state.setdefault("sos_active", False)
    state.setdefault("sos_phase", "LOBBY") # LOBBY, NEGOTIATION, RESULTS
    state.setdefault("sos_config", {
        "buy_in": 100,
        "is_percent": False,
        "house_bonus": 200,
        "pref_size": 3,
        "item_prices": {
            "peep": 2,
            "shield": 1,
            "insurance": 1,
            "tip": 1
        }
    })
    state.setdefault("sos_groups", []) # This will store the actual game data
    
    return state

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

def calculate_mission_value(base_val, passes, is_failure=False):
    """The 'Hot Potato' Compound Math"""
    safe_passes = min(passes, 5)
    multiplier = 1.5 ** safe_passes
    val = base_val * multiplier
    if is_failure:
        # Failure is 50% of the current Success value, but negative
        return -round(val * 0.5)
    return round(val)

def check_mafia_unanimous(mafia_votes):
    """
    mafia_votes: a dict of {mafia_player_name: voted_victim_name}
    Returns victim_name if unanimous, otherwise None.
    """
    votes = list(mafia_votes.values())
    if not votes:
        return None
    if all(v == votes[0] for v in votes) and votes[0] is not None:
        return votes[0]
    return None

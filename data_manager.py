import json
import os

STATE_FILE = "game_state.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        # Initialize a blank state if it doesn't exist
        return {"players": {}, "audit_log": [], "used_ids": [], "mafia_active": False}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

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

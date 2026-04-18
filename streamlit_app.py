import streamlit as st
import random
import json
import time
from data_manager import load_state, save_state, calculate_mission_value

# --- 1. INITIALIZATION ---
if "missions_library" not in st.session_state:
    with open("missions.json", "r") as f:
        st.session_state["missions_library"] = json.load(f)


# --- 2. LOGIN SCREEN FUNCTION ---
def login_screen():
    st.title("SideQuest")
    state = load_state()
    player_list = sorted(list(state["players"].keys()))

    tab1, tab2 = st.tabs(["Returning Player", "Register New Player"])

    with tab1:
        with st.form("login_returning"):
            name = st.selectbox("Select your Name", options=[""] + player_list)
            pin = st.text_input("Enter 4-Digit PIN", type="password", key="login_pin")
            if st.form_submit_button("Login"):
                if name != "" and state["players"][name]["pin"] == pin:
                    st.session_state["user"] = name
                    st.rerun()
                else:
                    st.error("Invalid Credentials")

    with tab2:
        with st.form("register_new"):
            new_name = st.text_input("Full Name").strip()
            new_pin = st.text_input("Set 4-Digit PIN", type="password", max_chars=4)
            if st.form_submit_button("Create Account"):
                if new_name and len(new_pin) == 4 and new_name not in state["players"]:

                    # --- NEW: AUTO-ADMIN FOR FIRST PLAYER ---
                    is_first_player = len(state["players"]) == 0

                    state["players"][new_name] = {
                        "pin": new_pin, "points": 0, "stars": 2,
                        "is_admin": is_first_player,  # <--- Set to True if database is empty
                        "is_judge": is_first_player,  # <--- Usually Admin is also Judge
                        "is_alive": True, "has_shield": False,
                        "active_buffs": {"muzzled_until": None, "taxed_by": None},
                        "active_slots": {
                            "slot_1": {"id": None, "passes": 0, "type": "slip_it_in"},
                            "slot_2": {"id": None, "passes": 0, "type": "convince_me"},
                            "slot_3": {"id": None, "passes": 0, "type": "trivia"}
                        },
                        "completed_ids": []
                    }
                    save_state(state)
                    st.session_state["user"] = new_name
                    st.rerun()
                else:
                    st.error("Invalid name or PIN (or name already taken)")


# --- 3. MISSION DASHBOARD FUNCTION ---
def display_dashboard():
    state = load_state()
    user = st.session_state["user"]
    player_data = state["players"][user]

    # --- NEW: STAFF GATEKEEPER ---
    if player_data.get("is_admin") or player_data.get("is_judge"):
        st.title(f"Staff Dashboard: {user}")
        st.info(
            "👋 You are registered as a **Judge/Admin**. You are not an active competitor in the missions or point-scoring.")

        st.subheader("Quick Actions")
        if player_data.get("is_admin"):
            st.write("Manage the game, roles, and system resets.")
            # This is a helpful tip since the Menu is in the sidebar
            st.caption("Use the sidebar to access the **Admin Portal**.")

        if player_data.get("is_judge"):
            st.write("You have access to Judge Tools in the Admin Portal to adjust points and stars.")

        # Optional: Show the Global Broadcast here too so Staff can see what they sent
        global_ev = state.get("global_event", {})
        if global_ev.get("broadcast_message"):
            st.warning(f"🚨 **ANNOUNCEMENT:** {global_ev['broadcast_message']}")

        return  # STOP HERE for Staff. Don't run the mission code below.

    missions = st.session_state["missions_library"]

    #---Global announcement---
    global_ev = state.get("global_event", {})
    broadcast = global_ev.get("broadcast_message")
    
    if broadcast:
        st.warning(f"🚨 **ANNOUNCEMENT:** {broadcast}")

    st.header(f"Dashboard: {user}")

    # --- COLLAPSIBLE LEADERBOARD ---
    with st.expander("📊 View Leaderboard & Standings"):
        leaderboard_data = []
        for p_name, p_info in state["players"].items():
            # Filter out Admin/Judge
            if not p_info.get("is_admin") and not p_info.get("is_judge"):
                leaderboard_data.append({
                    "Rank": 0, 
                    "Player": p_name,
                    "Points": p_info["points"]
                })
        
        # Sort by Points descending
        leaderboard_data = sorted(leaderboard_data, key=lambda x: x["Points"], reverse=True)
        
        # Assign Ranks
        for i, entry in enumerate(leaderboard_data):
            entry["Rank"] = i + 1

        # Using use_container_width=True makes it look better on mobile phones!
        st.dataframe(leaderboard_data, use_container_width=True, hide_index=True)

    #---User points and stars---
    c_m1, c_m2 = st.columns(2)
    c_m1.metric("Points", player_data["points"])
    c_m2.metric("Stars", player_data["stars"])

    # --- NEW: STAR TRANSFER TOOL ---
    with st.expander("🎁 Gift a Star"):
        if player_data["stars"] > 0:
            # Filter targets: No Admins, No Judges, and Not Yourself
            gift_targets = [
                p for p, info in state["players"].items() 
                if p != user and not info.get("is_admin") and not info.get("is_judge")
            ]
            
            target_col, button_col = st.columns([2, 1])
            
            recipient = target_col.selectbox(
                "Recipient",
                options=["Select Name"] + gift_targets,
                key="gift_recipient_select",
                label_visibility="collapsed"
            )
            
            if button_col.button("Send 1 ⭐", use_container_width=True):
                if recipient != "Select Name":
                    # Execute Transfer
                    player_data["stars"] -= 1
                    state["players"][recipient]["stars"] += 1
                    
                    # Log it
                    state["audit_log"].insert(0, f"🎁 {user} gifted a star to {recipient}!")
                    
                    save_state(state)
                    st.toast(f"Star sent to {recipient}!", icon="✨")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Select someone first!")
        else:
            st.info("You need at least 1 Star to send a gift.")

    st.divider()
    
    st.subheader("Your Active Missions")
    
    # Get the global list of what is turned off
    disabled_types = state.get("disabled_types", [])

    for slot_key, slot_info in player_data["active_slots"].items():
        # --- 1. GLOBAL DISABLE CHECK ---
        if slot_info["type"] in disabled_types:
            st.warning(f"⚠️ {slot_info['type'].replace('_', ' ').title()} is currently disabled by Admin.")
            continue # Skip this slot and move to the next one

        # --- 2. ASSIGN NEW MISSION IF EMPTY ---
        if slot_info["id"] is None:
            user_completed = player_data.get("completed_ids", [])
            available = [
                m for m in missions[slot_info["type"]]
                if m["id"] not in user_completed
            ]

            if available:
                new_m = random.choice(available)
                slot_info["id"] = new_m["id"]
                save_state(state)
                st.rerun()

        m_data = next((m for m in missions[slot_info["type"]] if m["id"] == slot_info["id"]), None)
        if not m_data: continue

        base_pts = m_data.get("points", 20)
        win_val = calculate_mission_value(base_pts, slot_info["passes"])
        fail_val = calculate_mission_value(base_pts, slot_info["passes"], is_failure=True)
        pass_cost = slot_info["passes"] + 1

        with st.expander(f"{slot_info['type'].replace('_', ' ').title()}", expanded=True):
            st.write(f"**Task:** {m_data.get('text', m_data.get('question'))}")

            # --- 1. SPECIAL UI FOR TRIVIA ---
            if slot_info["type"] == "trivia":
                options = m_data.get("options", [])
                correct_ans = m_data.get("answer")
                star_reward = m_data.get("stars", 0)

                # Display options as buttons
                cols = st.columns(len(options))
                for idx, opt in enumerate(options):
                    if cols[idx].button(opt, key=f"triv_{user}_{slot_key}_{idx}"):
                        if opt == correct_ans:
                            # SUCCESS: Award points and record completion
                            player_data["points"] += win_val
                            player_data["stars"] += star_reward
                            player_data["completed_ids"].append(m_data["id"])
                            state["audit_log"].insert(0, f"🧠 {user} answered Trivia correctly (+{win_val})")
                            st.success(f"Correct!+{win_val} points and +{star_reward} stars!")
                            time.sleep(2.0)
                        else:
                            penalty = int(win_val / 2) 
                            player_data["points"] -= penalty
                            state["audit_log"].insert(0, f"❌ {user} missed a Trivia question.")
                            st.error(f"Wrong! You lost {penalty} points. Don't worry, you'll get another chance.")
                            time.sleep(3.0)
                            

                        # Either way, clear the slot and save
                        slot_info["id"], slot_info["passes"] = None, 0
                        save_state(state)
                        st.rerun()

            # --- 2. STANDARD UI FOR MISSIONS (Slip It In / Convince Me) ---
            else:
                st.caption(f"Stakes: +{win_val} / {fail_val} | Pass: {pass_cost}⭐")
                
                # --- ADD THIS: The 'Victim' input for the Audit Log ---
                victim = st.selectbox(
                    "Who was the victim?", 
                    ["Select Name"] + [p for p in state["players"] if p != user], 
                    key=f"victim_{slot_key}",
                    help="Select the person you successfully tricked! (Note: You don't need to select a victim if you are clicking 'Failure')"
                )
                
                c1, c2, c3 = st.columns(3)
            
                if c1.button("Success ✅", key=f"win_{slot_key}"):
                    # Check if they actually selected someone
                    if victim == "Select Name":
                        st.error("You must select a victim to claim success!")
                    else:
                        player_data["points"] += win_val
                        player_data["stars"] += m_data.get("stars", 0)
                        player_data["completed_ids"].append(m_data["id"])
                        
                        # --- MODIFIED LOG: Include the target and the specific task ---
                        mission_text = m_data.get("text") or m_data.get("question")
                        log_entry = f"🎯 {user} got {victim}! Task: '{mission_text}' (+{win_val} pts)"
                        state["audit_log"].insert(0, log_entry)
                        
                        slot_info["id"], slot_info["passes"] = None, 0
                        save_state(state)
                        st.rerun()
            
                if c2.button("Failure ❌", key=f"fail_{slot_key}"):
                    # Failure doesn't usually need a victim, so we leave it simple
                    player_data["points"] += fail_val
                    state["audit_log"].insert(0, f"❌ {user} failed their mission and lost {abs(fail_val)} pts.")
                    slot_info["id"], slot_info["passes"] = None, 0
                    save_state(state)
                    st.rerun()

                with c3:
                    # Filter: Only include players who are NOT admins and NOT judges
                    potential_targets = [
                        p for p, info in state["players"].items() 
                        if p != user and not info.get("is_admin") and not info.get("is_judge")
                    ]
                    target = st.selectbox(
                        "Pass To", 
                        ["Select"] + potential_targets,
                        key=f"t_{slot_key}"
                    )
                    if st.button(f"Pass 🏹", key=f"p_{slot_key}"):
                        if target != "Select" and player_data["stars"] >= pass_cost:
                            player_data["stars"] -= pass_cost
                            vic = state["players"][target]
                            if vic.get("has_shield"):
                                vic["has_shield"] = False
                                slot_info["passes"] += 1
                                state["audit_log"].insert(0, f"🛡️ {target} bounced back to {user}!")
                            else:
                                vic["active_slots"][slot_key] = {"id": slot_info["id"],
                                                                 "passes": slot_info["passes"] + 1,
                                                                 "type": slot_info["type"]}
                                state["audit_log"].insert(0, f"🏹 {user} passed to {target}!")
                                slot_info["id"], slot_info["passes"] = None, 0
                            save_state(state)
                            st.rerun()

def display_sos_game(state, user):
    st.title("🎲 Split or Steal")
    
    # 1. Check if the game has actually started
    if state.get("sos_phase") == "LOBBY":
        st.info("The Admin is currently setting up the round. Please wait...")
        if st.button("Refresh"):
            st.rerun()
        return

    # 2. Find the user's group
    user_group = None
    for group in state.get("sos_groups", []):
        if user in group["members"]:
            user_group = group
            break
            
    if not user_group:
        st.warning("You are not participating in this round. Keep an eye on the Audit Log for the results!")
        return

    # 3. Game UI
    p_state = user_group["player_states"][user]
    opponents = [m for m in user_group["members"] if m != user]
    
    st.subheader(f"💰 The Pot: {user_group['pot']} Points")
    st.write(f"You are grouped with: **{', '.join(opponents)}**")
    
    # Show Star Items (Bribery / Tactical)
    st.divider()
    st.write("### 🛠 Tactical Items (Limit 1)")
    # We will build the Star Ability buttons in the next step! 
    # For now, let's just get the Split/Steal working.

    st.divider()
    
    # 4. The Decision
    if p_state["choice"] is not None:
        st.success(f"Locked in: **{p_state['choice']}**")
        st.info("Waiting for the Admin to end the round and reveal results.")
    else:
        col1, col2 = st.columns(2)
        if col1.button("🤝 SPLIT", use_container_width=True):
            p_state["choice"] = "Split"
            save_state(state)
            st.rerun()
        if col2.button("😈 STEAL", use_container_width=True, type="primary"):
            p_state["choice"] = "Steal"
            save_state(state)
            st.rerun()

    if st.button("Check for Updates / Refresh"):
        st.rerun()

# --- 4. ADMIN CONTROL PANEL FUNCTION ---
def display_admin(state):
    st.title("🕹️ Admin Control Panel")
    user = st.session_state["user"]
    
    # --- MISSION CATEGORY CONTROL ---
    st.subheader("Mission Management")
    all_types = ["slip_it_in", "convince_me", "trivia"]

    # Use .get() to prevent crashes if the key doesn't exist yet
    current_disabled = state.get("disabled_types", [])
    
    # We use multiselect to choose which ones to DISABLE
    disabled = st.multiselect(
        "Disable Mission Categories:",
        options=all_types,
        default=current_disabled,
        help="Missions in these categories will not appear for players."
    )

    if st.button("Update Global Mission Rules"):
        state["disabled_types"] = disabled
        save_state(state)
        st.toast("Rules Updated!", icon="✅")
        time.sleep(1.0)
        st.rerun()
    
    # --- 1. WIN CHECK CALCULATION ---
    alive_players = [p for p, d in state["players"].items() if d.get("is_alive") and d.get("role") != "Observer"]
    mafia_alive = [p for p in alive_players if state["players"][p].get("role") == "Mafia"]
    citizens_alive = [p for p in alive_players if state["players"][p].get("role") in ["Citizen", "Doctor", "Detective"]]

    # Logic to flip the switch to "Winner Declared"
    if state.get("mafia_active") and not state.get("winner_declared"):
        winner_team = None

        if not mafia_alive and len(alive_players) > 0:
            winner_team = "Citizens"
        elif len(mafia_alive) >= len(citizens_alive) and len(alive_players) > 0:
            winner_team = "Mafia"

        if winner_team:
            state["winner_declared"] = True

            # --- 🏆 DISTRIBUTE REWARDS ---
            for p, d in state["players"].items():
                role = d.get("role")
                if role == "Observer": continue

                # Check if player is on the winning team
                is_winner = (winner_team == "Mafia" and role == "Mafia") or \
                            (winner_team == "Citizens" and role in ["Citizen", "Doctor", "Detective"])

                if is_winner:
                    if d.get("is_alive"):
                        d["points"] += 40
                        d["stars"] += 3
                        state["audit_log"].insert(0, f"🏆 {p} earned 40pts/3⭐ for a Living Win!")
                    else:
                        d["points"] += 10
                        d["stars"] += 1
                        state["audit_log"].insert(0, f"🎗️ {p} earned 10pts/1⭐ for a Ghost Win!")

            save_state(state)
            st.rerun()

    # --- 2. VICTORY OVERLAY & RESET ---
    if state.get("winner_declared"):
        if not mafia_alive:
            st.balloons()
            st.success("🏆 VICTORY: Citizens Won!")
        else:
            st.snow()
            st.error("💀 VICTORY: Mafia Won!")

        # This button allows you to clear the game state so you can start over
        if st.button("🔄 Reset Game / Back to Lobby", key="reset_after_win", use_container_width=True):
            state["mafia_active"] = False
            state["winner_declared"] = False
            # Clear votes for the next round
            for p in state["players"]:
                state["players"][p]["mafia_vote"] = None
                state["players"][p]["last_checked"] = None
            save_state(state)
            st.rerun()

    st.divider()

    # --- 1. GOD VIEW (Admin Only Intel) ---
    st.subheader("👁️ Town Overview (Secret)")

    # Build the data for the God View table
    god_view_list = []
    for p_name, p_data in state["players"].items():
        # Determine the Power Display (Swing Vote indicator)
        weight = p_data.get("vote_weight", 1)
        power_display = "⚡ 2 (Swing)" if weight > 1 else "1"

        # Format the vote for easier reading
        current_vote = p_data.get("mafia_vote")
        vote_display = current_vote if current_vote not in [None, "None"] else "⚪ Pending"

        god_view_list.append({
            "Player": p_name,
            "Role": p_data.get("role", "N/A"),
            "Status": "✅ Alive" if p_data.get("is_alive", True) else "💀 DEAD",
            "Stars": p_data.get("stars", 0),
            "Vote": vote_display,
            "Power": power_display  # <--- Shows you the 3-star spent status
        })

    # Display as a clean table
    st.table(god_view_list)

    # --- 2. GLOBAL ANNOUNCEMENTS ---
    st.subheader("📣 Global Broadcast")
    
    # Show the current message so you know what's live
    current_msg = state.get("global_event", {}).get("broadcast_message", "")
    if current_msg:
        st.info(f"Currently Live: {current_msg}")
        if st.button("🗑️ Clear Current Alert"):
            state["global_event"]["broadcast_message"] = ""
            save_state(state)
            st.rerun()

    msg = st.text_input("Type a challenge for everyone:", key="admin_msg")
    if st.button("Send Alert"):
        if msg: # Only send if there is actually text
            if "global_event" not in state: state["global_event"] = {}
            state["global_event"]["broadcast_message"] = msg
            state["audit_log"].insert(0, f"📢 ADMIN: {msg}")
            save_state(state)
            st.success("Broadcast sent!")
            st.rerun() # Refresh to show the info box above

    st.divider()

    # --- 3. MAFIA CONTROLS ---
    st.subheader("🕵️ Mafia Management")

    if not state.get("mafia_active"):
        eligible = [p for p in state["players"] if
                    not state["players"][p].get("is_admin") and not state["players"][p].get("is_judge")]

        st.write(f"Eligible Players: {len(eligible)}")

        # 1. ADD THE QUANTITY SELECTOR
        # --- THE MATH  ---
        # If 6 players: (6-1) // 2 = 2 Mafia max.
        # If 5 players: (5-1) // 2 = 2 Mafia max.
        # If 7 players: (7-1) // 2 = 3 Mafia max.
        max_mafia = max(1, (len(eligible) - 1) // 2)

        num_mafia_input = st.number_input("Number of Mafia Members",
                                          min_value=1,
                                          max_value=max_mafia,
                                          value=1,
                                          help=f"Capped at {max_mafia} to ensure Citizens start with a majority.")

        if st.button("🚀 Start New Mafia Game", key="start_mafia_btn"):
            if len(eligible) >= 4:  # Lowered to 4 for more flexibility
                random.shuffle(eligible)
                state["winner_declared"] = False

                # 2. USE THE INPUT VALUE
                mafia_team = eligible[:num_mafia_input]

                # Assign Doctor and Detective from the remaining shuffled list
                # We use indexing to make sure we don't pick the same person twice
                remaining = eligible[num_mafia_input:]
                doctor = remaining[0] if len(remaining) > 0 else None
                detective = remaining[1] if len(remaining) > 1 else None

                for p in state["players"]:
                    state["players"][p]["last_checked"] = None
                    state["players"][p]["vote_weight"] = 1
                    state["players"][p]["mafia_vote"] = None

                    if p in eligible:
                        state["players"][p]["is_alive"] = True
                        if p in mafia_team:
                            state["players"][p]["role"] = "Mafia"
                        elif p == doctor:
                            state["players"][p]["role"] = "Doctor"
                        elif p == detective:
                            state["players"][p]["role"] = "Detective"
                        else:
                            state["players"][p]["role"] = "Citizen"
                    else:
                        state["players"][p]["role"] = "Observer"
                        state["players"][p]["is_alive"] = True

                state["mafia_active"] = True
                state["mafia_phase"] = "Night"
                state["mafia_log"] = [f"🌑 GAME START: {num_mafia_input} Mafia are among us!"]
                save_state(state)
                st.rerun()
            else:
                st.error(f"Need at least 4 players. You have {len(eligible)}.")

    else:
        # --- ACTIVE GAME CONTROLS ---
        c1, c2 = st.columns(2)
        # 1. Action Button (Changes based on Phase)
        if state.get("mafia_phase") == "Night":
            if c1.button("🌅 End Night & Process Kill", key="process_kill_btn", use_container_width=True):
                # --- 1. SAFETY CHECK ---
                if "mafia_log" not in state:
                    state["mafia_log"] = []

                # --- 2. GET ROLES/VOTES ---
                mafia_votes = {p: d["mafia_vote"] for p, d in state["players"].items() if
                               d.get("role") == "Mafia" and d["is_alive"]}
                from data_manager import check_mafia_unanimous
                target = check_mafia_unanimous(mafia_votes)

                protected = next((d["mafia_vote"] for p, d in state["players"].items() if
                                  d.get("role") == "Doctor" and d["is_alive"]), None)

                # --- 3. RESOLVE & LOG ---
                if target and target == protected:
                    state["mafia_log"].insert(0,
                                              f"🏥 SAVED: The Mafia tried to kill {target}, but the Doctor was there!")
                elif target:
                    state["players"][target]["is_alive"] = False
                    state["mafia_log"].insert(0, f"💀 MORNING: {target} was found dead. The Mafia struck!")
                else:
                    # Note: Added a more descriptive message for clarity
                    state["mafia_log"].insert(0, "🌅 MORNING: No one died. The Mafia couldn't agree on a target.")

                # --- 4. RESET FOR DAY ---
                state["mafia_phase"] = "Day"
                for p in state["players"]:
                    state["players"][p]["mafia_vote"] = None
                    # Just in case someone bought a swing vote during the night (which they shouldn't)
                    state["players"][p]["vote_weight"] = 1

                save_state(state)
                st.rerun()

        else:
            # DAY TO NIGHT (Process Town Vote)
            if c1.button("🌙 Set to NIGHT (Process Town Vote)", key="btn_set_night", use_container_width=True):
                # --- WEIGHTED VOTE COUNTING ---
                vote_tally = {}

                # 1. Ensure the log exists
                if "mafia_log" not in state:
                    state["mafia_log"] = []

                for p, d in state["players"].items():
                    if d.get("is_alive") and d.get("mafia_vote") not in [None, "None"]:
                        target = d["mafia_vote"]
                        weight = d.get("vote_weight", 1)  # Default to 1 if not set
                        vote_tally[target] = vote_tally.get(target, 0) + weight

                if vote_tally:
                    max_votes = max(vote_tally.values())
                    leaders = [who for who, count in vote_tally.items() if count == max_votes]

                    if len(leaders) == 1:
                        victim = leaders[0]
                        state["players"][victim]["is_alive"] = False

                        # Check if any living player actually used a weight > 1 this round
                        swing_used = any(
                            d.get("vote_weight", 1) > 1 for p, d in state["players"].items() if d.get("is_alive"))

                        if swing_used:
                            msg = f"⚖️ EXECUTION: {victim} was lynched (Weighted Vote!)."
                        else:
                            msg = f"⚖️ EXECUTION: {victim} was lynched by majority vote."

                        state["mafia_log"].insert(0, msg)
                    else:
                        state["mafia_log"].insert(0, f"⚖️ TIE: The town was split. No one was executed.")
                else:
                    state["mafia_log"].insert(0, "🌙 NIGHT FALLS: No votes were cast.")

                # Reset phase and votes
                state["mafia_phase"] = "Night"
                for p in state["players"]:
                    state["players"][p]["mafia_vote"] = None
                    state["players"][p]["vote_weight"] = 1  # Reset weight for everyone
                save_state(state)
                st.rerun()

        # 3. Emergency Stop Button
        if c2.button("🛑 END GAME", key="btn_end_mafia", use_container_width=True):
            state["mafia_active"] = False
            if "mafia_log" not in state:
                state["mafia_log"] = []
            state["mafia_log"].insert(0, "🛑 GAME OVER: The Mafia game has been ended by the Admin.")
            save_state(state)
            st.rerun()

    # --- 4. SPLIT OR STEAL CONTROLS ---
    st.divider()
    admin_sos_panel(state) # This calls the panel we built earlier
    
    st.divider()  # This divider is now outside the if/else logic
    
    # --- 4. PLAYER ADJUSTMENTS ---
    st.subheader("⚖️ Judge Tools")
    target_player = st.selectbox("Select Player", options=list(state["players"].keys()), key="adjust_target")
    col_p, col_s = st.columns(2)
    amt_pts = col_p.number_input("Points", value=0, key="adj_pts")
    amt_stars = col_s.number_input("Stars", value=0, key="adj_stars")

    # Add a unique key so Streamlit doesn't get confused
    if st.button("Apply Adjustments", key="admin_apply_adjustments_btn"):
        state["players"][target_player]["points"] += amt_pts
        state["players"][target_player]["stars"] += amt_stars
        state["audit_log"].insert(0, f"⚖️ ADMIN adjusted {target_player}: {amt_pts}pts, {amt_stars}⭐")
        save_state(state)
        st.rerun()

#---Player Maintenance---
    st.divider()
    st.subheader("🛠️ System Maintenance")

    # This creates two tabs: one for individual player fixes, one for the Nuke
    tab_manage, tab_nuke = st.tabs(["Manage Players", "Reset System"])

    with tab_manage:
        st.write("Force a player to become a Ghost and reassign their role if necessary.")

        # Only show players who are currently ALIVE and part of the active game
        alive_in_game = [p for p, d in state["players"].items() if d.get("is_alive") and d.get("role") != "Observer"]

        target_to_kill = st.selectbox("Select Player to 'Ghost'",
                                      options=["Select"] + alive_in_game,
                                      key="force_kill_select")

        if st.button("💀 Ghost and Reassign Role", type="secondary"):
            if target_to_kill != "Select":
                old_role = state["players"][target_to_kill].get("role")
                state["players"][target_to_kill]["is_alive"] = False

                # --- ROLE REASSIGNMENT LOGIC ---
                if old_role in ["Doctor", "Detective", "Mafia"]:
                    # Find living Citizens to inherit the role
                    eligible_heirs = [p for p, d in state["players"].items()
                                      if d.get("is_alive") and d.get("role") == "Citizen"]

                    if eligible_heirs:
                        new_heir = random.choice(eligible_heirs)
                        state["players"][new_heir]["role"] = old_role

                        # Log it for the game history
                        state["mafia_log"].insert(0,
                                                  f"🎭 ROLE SHIFT: {target_to_kill} ({old_role}) left. Someone else is the new {old_role}!")
                        
                    else:
                        state["mafia_log"].insert(0,
                                                  f"⚠️ ROLE LOST: {target_to_kill} was the {old_role}, but no citizens were left.")

                state["audit_log"].insert(0, f"💀 ADMIN forced {target_to_kill} to Ghost status.")
                save_state(state)
                st.success(f"{target_to_kill} is now a Ghost. Role reassigned if applicable.")
                st.rerun()

    with tab_nuke:
        # --- YOUR EXISTING NUKE CODE GOES HERE ---
        st.warning("⚠️ **DANGER:** This wipes ALL players and ALL scores.")
        confirm_nuke = st.checkbox("I confirm I want to destroy all data.")

        if st.button("🔥 PERMANENT SYSTEM RESET", type="primary", disabled=not confirm_nuke):
            default_state = {
                "players": {},
                "used_ids": [],
                "audit_log": ["🚀 System Reinitialized"],
                "mafia_active": False,
                "mafia_phase": "Night",
                "mafia_log": [],
                "winner_declared": False,
                "global_event": {"broadcast_message": ""}
            }
            save_state(default_state)
            if "user" in st.session_state:
                del st.session_state["user"]
            st.success("Database wiped. Redirecting...")
            st.rerun()

def admin_sos_panel(state):
    st.header("🎲 Split or Steal: Admin Control")
    
    # 1. Global Toggle
    sos_on = st.toggle("Activate Split or Steal Tab for Players", value=state.get("sos_active", False))
    if sos_on != state.get("sos_active"):
        state["sos_active"] = sos_on
        save_state(state)
        st.rerun()

    if not state.get("sos_active"):
        st.info("Game tab is currently hidden from players.")
        return

    # 2. Configuration Form
    with st.form("sos_config_form"):
        st.subheader("Settings")
        col1, col2 = st.columns(2)
        
        buy_in = col1.number_input("Buy-In Amount", min_value=0, value=state["sos_config"]["buy_in"])
        is_percent = col1.checkbox("Use % for Buy-In", value=state["sos_config"]["is_percent"])
        bonus = col2.number_input("House Bonus Points", min_value=0, value=state["sos_config"]["house_bonus"])
        pref_size = col2.selectbox("Preferred Group Size", [3, 2], index=0 if state["sos_config"]["pref_size"] == 3 else 1)
        
        st.write("**Star Item Pricing**")
        p_cols = st.columns(4)
        peep_p = p_cols[0].number_input("Peep", 0, 10, state["sos_config"]["item_prices"]["peep"])
        shield_p = p_cols[1].number_input("Shield", 0, 10, state["sos_config"]["item_prices"]["shield"])
        insur_p = p_cols[2].number_input("Insurance", 0, 10, state["sos_config"]["item_prices"]["insurance"])
        tip_p = p_cols[3].number_input("Tip", 0, 10, state["sos_config"]["item_prices"]["tip"])
        
        if st.form_submit_button("Update Game Settings"):
            state["sos_config"] = {
                "buy_in": buy_in,
                "is_percent": is_percent,
                "house_bonus": bonus,
                "pref_size": pref_size,
                "item_prices": {"peep": peep_p, "shield": shield_p, "insurance": insur_p, "tip": tip_p}
            }
            save_state(state)
            st.success("Settings updated!")

    # 3. Player Selection & Start Game
    st.divider()
    st.subheader("Start New Round")
    
    # List all players who aren't admins (to keep it a player game)
    players = state["players"]
    eligible = [p for p in players if not players[p].get("is_admin")]
    
    selected_players = []
    cols = st.columns(3)
    for idx, name in enumerate(eligible):
        if cols[idx % 3].checkbox(name, key=f"sos_sel_{name}"):
            selected_players.append(name)
            
    if st.button("Generate Groups & Start Game", type="primary"):
        if len(selected_players) < 2:
            st.error("You need at least 2 players to play!")
        else:
            # We will build the 'start_sos_game' logic in the next step
            st.warning("Grouping logic coming in the next step!")

# --- 5. MAFIA GAME FUNCTION ---
def display_mafia():
    state = load_state()
    user = st.session_state["user"]
    player_data = state["players"].get(user, {})

    if not state.get("mafia_active"):
        st.info("The town is currently at peace.")
        return

    # 1. STATUS & ROLE CHECK
    user_role = player_data.get("role", "Citizen")
    is_alive = player_data.get("is_alive", True)

    # --- 2. GAME OVER REVEAL (PRIORITY 1) ---
    # Check this first so dead players see the victory screen!
    if state.get("winner_declared"):
        st.title("🏁 THE GAME HAS ENDED")
        alive_players = [p for p, d in state["players"].items() if
                         d.get("is_alive") and d.get("role") != "Observer"]
        mafia_alive = [p for p in alive_players if state["players"][p].get("role") == "Mafia"]

        if not mafia_alive:
            st.balloons()
            st.success("🏆 VICTORY! The Citizens have saved the town.")
        else:
            st.snow()
            st.error("💀 DEFEAT! The Mafia has taken control.")

        st.subheader("🗂️ Final Role Reveal:")
        for p, d in state["players"].items():
            if d.get("role") != "Observer":
                status = "✅ Alive" if d.get("is_alive") else "💀 Dead"
                st.write(f"**{p}** was the **{d['role']}** ({status})")

        st.divider()
        st.subheader("📜 Final Game History")
        for entry in state.get("mafia_log", []):
            st.caption(entry)
        return

    # --- 3. THE GHOST VIEW GATEKEEPER (PRIORITY 2) ---
    if not is_alive:
        st.error("💀 YOU ARE DEAD")
        st.subheader("👻 Ghost View")
        st.write("You can no longer vote or participate, but you can watch the drama unfold!")
        st.divider()
        st.subheader("📜 Game History")
        for entry in state.get("mafia_log", []):
            st.caption(entry)
        return

    current_phase = state.get("mafia_phase", "Day")

    # --- NEW: INSTRUCTIONS EXPANDER ---
    with st.expander("📖 How to Play & Role Guide", expanded=False):
        st.markdown("""
            ### 🎮 The Goal
            * **Citizens:** Identify and vote out all Mafia members. 
            * **Mafia:** Eliminate Citizens until your numbers are equal.
            
            ### Game Phases
            * **🌅 Day:** All players have the option to vote during the day on who they'd like to kill. Player with the most votes cast against them will die when night falls.
            * **🌙 Night:** This is when Mafia members, the Detective, and Doctor are tasked with selecting players. Mafia will also vote during the night on who they'd like to take out. This must be unanimously decided before night ends.
            * The duration of each phase will vary, and players will typically be given a warning before a phase switch. But also maybe not....
                        
            ### 🎭 Role Abilities
            * **💀 Mafia:** Members collectively choose one person to kill each night. 
            * **🕵️ Detective:** Each Night, choose one person to investigate. You will see their true role the next Morning. 
            * **🏥 Doctor:** Each Night, choose one person to protect. If the Mafia targets them, they will survive.
            * **🚀 Swing Vote:** During the Day, any player can spend **3 Stars** to make their vote count as **2**!

            ### Optional Rule
            * **Hard Core Mode:** For a member of the mafia to officially kill a citizen they must physically touch their victim during the night phase before they vote. (regulated through the good ol honor system)

            ### ⚖️ Rewards
            * **Winning Team (Alive):** +40 pts / +3 ⭐
            * **Winning Team (Ghost):** +10 pts / +1 ⭐
            """)

    st.divider()

    # --- 4. LIVE GAME UI (Only reached if active AND alive) ---
    with st.expander("🔒 Tap to Reveal Your Secret Identity"):
        st.caption(f"Your Secret Role: {user_role}")
        # 2. TEAM INTEL
        if user_role == "Mafia":
            teammates = [p for p, d in state["players"].items() if d.get("role") == "Mafia"]
            st.warning(f"💀 **MAFIA TEAM:** {', '.join(teammates)}")
        elif user_role == "Citizen":
            st.info("🕵️ **CITIZEN:** Try to figure out who the Mafia is!")
            
    
    if current_phase == "Night":
        st.subheader("🌙 Night Phase")

        with st.expander("Action Portal"):
            # --- MAFIA ACTION ---
            if user_role == "Mafia":
                targets = [p for p, d in state["players"].items() if d.get("is_alive") and d.get("role") != "Mafia"]
                vote = st.selectbox("Choose a target to eliminate:", ["None"] + targets)
                if st.button("Confirm Kill Vote"):
                    player_data["mafia_vote"] = vote
                    save_state(state);
                    st.success(f"Voted for {vote}")
    
            #---Doctor ACTION---
            elif user_role == "Doctor":
                current_save = player_data.get("mafia_vote")
                if current_save and current_save != "None":
                    st.success(f"🏥 You are currently protecting **{current_save}**.")
    
                targets = [p for p, d in state["players"].items() if d.get("is_alive")]
                save_choice = st.selectbox("Choose (or change) who to protect:", ["None"] + targets)
                if st.button("Lock In Protection"):
                    player_data["mafia_vote"] = save_choice
                    save_state(state)
                    st.success(f"Protection updated!")
                    st.rerun()
    
            # --- DETECTIVE ACTION (NIGHT) ---
            elif user_role == "Detective":
                # 1. Check if they have a target selected
                current_target = player_data.get("mafia_vote")
    
                if current_target and current_target != "None":
                    st.info(f"🔍 You are currently set to investigate **{current_target}**.")
                else:
                    st.write("🔍 You haven't chosen a target to tail yet.")
    
                # 2. Keep the menu open so they can change their mind
                targets = [p for p, d in state["players"].items() if d.get("is_alive") and p != user]
                investigate = st.selectbox("Choose (or change) your investigation target:", ["None"] + targets)
    
                if st.button("Lock In Investigation"):
                    if investigate != "None":
                        player_data["mafia_vote"] = investigate
                        # We update 'last_checked' now, but the Day Phase logic
                        # won't show the report until state["mafia_phase"] == "Day"
                        player_data["last_checked"] = investigate
                        save_state(state)
                        st.success(f"Target updated to {investigate}!")
                        st.rerun()
    
            else:
                st.write("The town is asleep. Stay quiet...")

    # 4. DAY PHASE (Town Square)
    else:
        st.subheader("☀️ Day Phase: Town Square")
        st.write("Discuss! Who is the most suspicious?")

        # --- 1. DETECTIVE'S PRIVATE REPORT (Keep this at the top) ---
        if user_role == "Detective":
            report_target = player_data.get("last_checked")
            if report_target and report_target in state["players"]:
                target_role = state["players"][report_target].get("role")
                st.markdown("### 🔍 Morning Investigation Report")
                if target_role == "Mafia":
                    st.error(f"REPORT: {report_target} is **MAFIA**.")
                else:
                    st.success(f"REPORT: {report_target} is a **Citizen**.")
                st.caption("Keep this info secret or share it wisely!")

        st.divider()

        # --- 2. PERSISTENT VOTING LOGIC ---
        # Get data from the state
        current_vote = player_data.get("mafia_vote")
        has_voted = current_vote not in [None, "None"]
        current_weight = player_data.get("vote_weight", 1)
        user_stars = player_data.get("stars", 0)

        if has_voted:
            # This shows up if they leave the tab and come back
            vote_type = "🚀 SWING VOTE" if current_weight > 1 else "Standard Vote"
            st.success(f"✅ **Your vote is locked in for: {current_vote}**")
            st.info(f"Vote Type: {vote_type}")

            if st.button("🔄 Change Vote"):
                # Clear the vote so the buttons reappear
                player_data["mafia_vote"] = None
                # We reset weight to 1, but stars are already spent (prevents exploits)
                player_data["vote_weight"] = 1
                save_state(state)
                st.rerun()
        else:
            # Show the selection UI if no vote is recorded
            targets = [p for p, d in state["players"].items() if d.get("is_alive") and p != user]
            nomination = st.selectbox("Nominate someone to eliminate:", ["None"] + targets, key="town_day_vote")

            col1, col2 = st.columns(2)

            # Regular Vote
            if col1.button("Cast Standard Vote", key="confirm_day_btn", use_container_width=True):
                if nomination != "None":
                    player_data["mafia_vote"] = nomination
                    player_data["vote_weight"] = 1
                    save_state(state)
                    st.rerun()  # Rerun to switch to the 'Locked' view
                else:
                    st.warning("Please select a target first.")

            # Swing Vote
            if col2.button("🚀 Cast Swing Vote (3 Stars)", help="Costs 3 stars. Counts twice!", use_container_width=True):
                if nomination == "None":
                    st.warning("Select a target first!")
                elif user_stars >= 3:
                    player_data["stars"] = user_stars - 3
                    player_data["mafia_vote"] = nomination
                    player_data["vote_weight"] = 2
                    save_state(state)
                    st.balloons()
                    st.rerun()  # Rerun to switch to the 'Locked' view
                else:
                    st.error(f"Not enough stars! You have {user_stars}.")

        st.divider()
        st.caption("Standard Vote counts as 1 vote.")
        st.caption("Swing Vote counts as 2 votes.")
        st.caption("It costs 3 stars EACH time you lock in a Swing Vote even if you change your nomination.")
        st.caption(f"You currently have {user_stars} stars available.")

        # At the end of display_mafia()
        st.divider()
        st.subheader("📜 Game History")
        mafia_history = state.get("mafia_log", [])

        if mafia_history:
            # Join the logs with newlines or display as a list
            for entry in mafia_history:
                st.caption(entry)
        else:
            st.write("The history is currently empty.")

# --- 6. MAIN APP FLOW ---
state = load_state()

if "user" not in st.session_state:
    login_screen()
else:
    user = st.session_state["user"]
    player_data = state["players"].get(user, {})

    st.sidebar.title("Menu")
    menu_options = ["Dashboard", "Audit Log"]

    if state.get("mafia_active"):
        menu_options.append("Mafia Game")
    if state.get("sos_active"):
        menu_options.append("Split or Steal")
    if player_data.get("is_admin"):
        menu_options.append("Admin Portal")

    choice = st.sidebar.radio("Go to", menu_options)

    if st.sidebar.button("Logout"):
        del st.session_state["user"];
        st.rerun()

    if choice == "Dashboard":
        display_dashboard()
    elif choice == "Audit Log":
        st.title("📜 Public Audit Log")
        for entry in state.get("audit_log", []):
            st.write(entry)
    elif choice == "Mafia Game":
        display_mafia()
    elif choice == "Split or Steal":
        display_sos_game(state, user)
    elif choice == "Admin Portal":
        display_admin(state)

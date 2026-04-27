"""
Clan Tracking Commands — ported from Req and Leave bot.

Commands:
  /clantrack <clan_tag> — Start tracking a clan for join/leave/promotion events
  /deltrack            — Stop tracking the current clan
  /crnttrack           — Show currently tracked clan details

Background job runs every 60s to detect:
  - Members joining / leaving
  - Role promotions / demotions
"""

import json
import os
import logging
import coc
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime, timezone

from coc_api import get_clan_war
from commands.clan import _parse_coc_time

# ── Config ───────────────────────────────────────────────────────────────────
DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clan_data.json")

ROLE_ORDER = {'Member': 0, 'Elder': 1, 'Co-Leader': 2, 'Leader': 3}
ROLE_NAMES = {
    'Member': 'Member',
    'Elder': 'Elder',
    'Co-Leader': 'Co-Leader',
    'Leader': 'Leader'
}

OWNER_ID = int(os.getenv('OWNER_ID', '0'))
CHAT_ID = os.getenv('CHAT_ID')

DEFAULT_NOTIFICATIONS = {"join_leave": True, "war": True}


def _get_notif_prefs(data: dict) -> dict:
    """Get notification preferences, defaulting to all-on."""
    return data.get("notifications", DEFAULT_NOTIFICATIONS.copy())


def _track_config_markup(data: dict) -> InlineKeyboardMarkup:
    """Build toggle buttons showing current notification state."""
    prefs = _get_notif_prefs(data)
    jl = prefs.get("join_leave", True)
    war = prefs.get("war", True)
    all_on = jl and war

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{'✅' if jl else '❌'} Join/Leave", callback_data="tkcfg:join_leave"),
            InlineKeyboardButton(f"{'✅' if war else '❌'} War", callback_data="tkcfg:war"),
        ],
        [
            InlineKeyboardButton(f"{'✅' if all_on else '⬜'} All", callback_data="tkcfg:all"),
        ]
    ])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _player_link(name: str, tag: str) -> str:
    clean_tag = tag.replace("#", "%23")
    return f"[{name}](https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={clean_tag})"


def _load_data() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                # Migration: old format stored members as plain strings
                if "members" in data:
                    migrated = {}
                    for tag, val in data["members"].items():
                        if isinstance(val, str):
                            migrated[tag] = {"name": val, "role": "member"}
                        else:
                            migrated[tag] = val
                    data["members"] = migrated
                return data
        except (json.JSONDecodeError, IOError):
            pass
    return {"tracked_tag": None, "members": {}, "initiated_by": "System"}


def _save_data(data: dict):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)


async def _get_player_info(coc_client: coc.Client, player_tag: str):
    """Fetch TH level and XP level for a player."""
    try:
        player = await coc_client.get_player(player_tag)
        return player.town_hall, player.exp_level
    except Exception:
        return "N/A", "N/A"


# ── COC Client Setup ────────────────────────────────────────────────────────

async def setup_coc_client(app):
    """Called during post_init to login to Supercell API."""
    email = os.getenv('COC_EMAIL')
    password = os.getenv('COC_PASSWORD')
    if not email or not password:
        logging.warning("COC_EMAIL / COC_PASSWORD not set - tracking commands disabled.")
        return

    coc_client = coc.Client(load_game_data=coc.LoadGameData.always)
    try:
        await coc_client.login(email, password)
        app.bot_data["coc_client"] = coc_client
        logging.info("Successfully logged into Clash of Clans API.")
    except Exception as e:
        logging.error(f"COC Login Error: {e}")

    # Restore tracking chat_id from disk so maintenance notifier works after restart
    try:
        saved = _load_data()
        if saved.get("chat_id"):
            app.bot_data["tracking_chat_id"] = saved["chat_id"]
            logging.info(f"Restored tracking chat_id: {saved['chat_id']}")
    except Exception:
        pass


# ── Background Job ──────────────────────────────────────────────────────────

async def check_clan_changes(context: ContextTypes.DEFAULT_TYPE):
    """Job to check for clan joins/leaves/promotions every 30 seconds."""
    data = _load_data()
    clan_tag = data.get("tracked_tag")
    if not clan_tag:
        return

    coc_client = context.bot_data.get("coc_client")
    if not coc_client:
        return

    chat_id = data.get("chat_id") or CHAT_ID
    if not chat_id:
        return

    # Cache chat_id in bot_data so maintenance notifier can use it
    context.bot_data["tracking_chat_id"] = chat_id

    try:
        print(f"--- [Job] Starting Clan Scan for {clan_tag} ---", flush=True)
        clan = await coc_client.get_clan(clan_tag)
        current_members = {m.tag: m for m in clan.members}

        # First run: just save members and return
        if "members" not in data or not data["members"]:
            data["members"] = {t: {"name": m.name, "role": str(m.role)} for t, m in current_members.items()}
            
            war_data = await get_clan_war(clan_tag)
            if "error" not in war_data and war_data.get("state") == "preparation":
                data["last_war_opponent"] = war_data.get("opponent", {}).get("tag", "")
            else:
                data["last_war_opponent"] = ""
                
            _save_data(data)
            print(f"First run for {clan_tag}: Saved {len(current_members)} members.", flush=True)
            return

        previous_members = data["members"]
        prev_tags = set(previous_members.keys())
        curr_tags = set(current_members.keys())

        notif = _get_notif_prefs(data)

        # 1. Detect members who LEFT
        for tag in (prev_tags - curr_tags):
            name = previous_members[tag]["name"]
            if notif.get("join_leave", True):
                th, xp = await _get_player_info(coc_client, tag)
                link = _player_link(name, tag)
                text = (
                    f"❌ {link} has left the clan.\n"
                    f"🏠 Town Hall: {th}\n"
                    f"⭐ XP Level: {xp}"
                )
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown', disable_web_page_preview=True)
            safe_name = name.encode('ascii', 'ignore').decode()
            print(f"Log: {safe_name} left.", flush=True)

        # 2. Detect members who JOINED
        for tag in (curr_tags - prev_tags):
            m = current_members[tag]
            if notif.get("join_leave", True):
                th, xp = await _get_player_info(coc_client, tag)
                link = _player_link(m.name, tag)
                text = (
                    f"✅ {link} has joined the clan!\n"
                    f"🏠 Town Hall: {th}\n"
                    f"⭐ XP Level: {xp}"
                )
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown', disable_web_page_preview=True)
            safe_name = m.name.encode('ascii', 'ignore').decode()
            print(f"Log: {safe_name} joined.", flush=True)

        # 3. Detect promotions / demotions
        changes_detected = False
        for tag in (prev_tags & curr_tags):
            old_role = previous_members[tag].get("role", "Member")
            new_role = str(current_members[tag].role)

            if old_role != new_role:
                changes_detected = True
                name = current_members[tag].name
                if notif.get("join_leave", True):
                    link = _player_link(name, tag)
                    old_rank = ROLE_ORDER.get(old_role, 0)
                    new_rank = ROLE_ORDER.get(new_role, 0)
                    pretty_new = ROLE_NAMES.get(new_role, new_role.capitalize())

                    if new_rank > old_rank:
                        text = f"🎖️ {link} has been *promoted* to {pretty_new}!"
                    else:
                        text = f"📉 {link} has been *demoted* to {pretty_new}."

                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown', disable_web_page_preview=True)
                safe_name = name.encode('ascii', 'ignore').decode()
                print(f"Log: {safe_name} role changed from {old_role} to {new_role}.", flush=True)

        # 4. Check for new War (Preparation)
        war_data = await get_clan_war(clan_tag)
        war_notif = notif.get("war", True)
        if "error" not in war_data:
            state = war_data.get("state")
            o_tag = war_data.get("opponent", {}).get("tag", "")
            
            if state == "preparation":
                if data.get("last_war_opponent") != o_tag:
                    data["last_war_opponent"] = o_tag
                    changes_detected = True
                    
                    if war_notif:
                        o_name = war_data.get("opponent", {}).get("name", "Unknown")
                        team_size = war_data.get("teamSize", "?")
                        o_clean = o_tag.replace("#", "")
                        start_time_str = war_data.get("startTime", "")
                        s_dt = _parse_coc_time(start_time_str)
                        
                        if s_dt:
                            diff = s_dt - datetime.now(timezone.utc)
                            hours, rem = divmod(int(diff.total_seconds()), 3600)
                            if hours > 0:
                                prep_str = f"{hours} hours"
                            else:
                                prep_str = f"{rem // 60} minutes"
                        else:
                            prep_str = "Unknown"
                            
                        war_text = (
                            f"⚔️ **War Found!**\n"
                            f"**{clan.name}** vs **[{o_name}](https://link.clashofclans.com/en?action=OpenClanProfile&tag=%23{o_clean})**\n"
                            f"👥 Size: {team_size}v{team_size}\n"
                            f"⏳ Preparation Time: {prep_str}"
                        )
                        await context.bot.send_message(chat_id=chat_id, text=war_text, parse_mode='Markdown', disable_web_page_preview=True)
                        safe_o = o_name.encode('ascii', 'ignore').decode()
                        print(f"Log: War found against {safe_o}", flush=True)
            elif state == "inWar":
                # ── War Feed: Detect and announce new attacks ────────
                known_orders = set(data.get("last_war_attacks", []))
                all_clan_members = war_data.get("clan", {}).get("members", [])
                all_opp_members = war_data.get("opponent", {}).get("members", [])

                # Build a lookup for defender info
                all_war_members = {
                    m.get("tag", ""): m for m in (all_clan_members + all_opp_members)
                }

                new_attacks = []
                # Clan attacks
                for m in all_clan_members:
                    for atk in m.get("attacks", []):
                        order = atk.get("order", 0)
                        if order not in known_orders:
                            defender = all_war_members.get(atk.get("defenderTag", ""), {})
                            new_attacks.append({
                                "order": order,
                                "attacker": m.get("name", "Unknown"),
                                "attacker_th": m.get("townhallLevel", "?"),
                                "stars": atk.get("stars", 0),
                                "destruction": atk.get("destructionPercentage", 0),
                                "defender": defender.get("name", "Unknown"),
                                "defender_th": defender.get("townhallLevel", "?"),
                                "defender_pos": defender.get("mapPosition", "?"),
                                "is_clan": True,
                            })

                # Opponent attacks
                for m in all_opp_members:
                    for atk in m.get("attacks", []):
                        order = atk.get("order", 0)
                        if order not in known_orders:
                            defender = all_war_members.get(atk.get("defenderTag", ""), {})
                            new_attacks.append({
                                "order": order,
                                "attacker": m.get("name", "Unknown"),
                                "attacker_th": m.get("townhallLevel", "?"),
                                "stars": atk.get("stars", 0),
                                "destruction": atk.get("destructionPercentage", 0),
                                "defender": defender.get("name", "Unknown"),
                                "defender_th": defender.get("townhallLevel", "?"),
                                "defender_pos": defender.get("mapPosition", "?"),
                                "is_clan": False,
                            })

                # Sort new attacks by order and announce
                new_attacks.sort(key=lambda x: x["order"])
                for atk in new_attacks:
                    stars_str = "⭐" * atk["stars"] + "☆" * (3 - atk["stars"])
                    if atk["is_clan"]:
                        icon = "⚔️"
                        atk_text = (
                            f"{icon} **War Attack!**\n"
                            f"🛡️ **{atk['attacker']}** (TH{atk['attacker_th']}) attacked "
                            f"**{atk['defender']}** (TH{atk['defender_th']}) — Base #{atk['defender_pos']}\n"
                            f"{stars_str} | 💥 {atk['destruction']}%"
                        )
                    else:
                        icon = "🏴"
                        atk_text = (
                            f"{icon} **Enemy Attack!**\n"
                            f"🏴 **{atk['attacker']}** (TH{atk['attacker_th']}) attacked "
                            f"**{atk['defender']}** (TH{atk['defender_th']}) — Base #{atk['defender_pos']}\n"
                            f"{stars_str} | 💥 {atk['destruction']}%"
                        )
                    if war_notif:
                        await context.bot.send_message(
                            chat_id=chat_id, text=atk_text,
                            parse_mode='Markdown', disable_web_page_preview=True
                        )
                    known_orders.add(atk["order"])

                if new_attacks:
                    data["last_war_attacks"] = list(known_orders)
                    changes_detected = True
                    print(f"Log: Announced {len(new_attacks)} new war attack(s).", flush=True)

            elif state == "warEnded":
                # Clear war attack tracking when war ends
                if "last_war_attacks" in data:
                    data.pop("last_war_attacks")
                    changes_detected = True

                if data.get("last_war_opponent", "") != "":
                    clan_stars = war_data.get('clan', {}).get('stars', 0)
                    clan_dest = war_data.get('clan', {}).get('destructionPercentage', 0)
                    opp_stars = war_data.get('opponent', {}).get('stars', 0)
                    opp_dest = war_data.get('opponent', {}).get('destructionPercentage', 0)
                    
                    if clan_stars > opp_stars:
                        result_text = "🏆 **VICTORY!**"
                    elif opp_stars > clan_stars:
                        result_text = "💀 **DEFEAT**"
                    else:
                        if clan_dest > opp_dest:
                            result_text = "🏆 **VICTORY (Destruction Tiebreak)!**"
                        elif opp_dest > clan_dest:
                            result_text = "💀 **DEFEAT (Destruction Tiebreak)**"
                        else:
                            result_text = "🤝 **DRAW**"
                            
                    e_dt = _parse_coc_time(war_data.get('endTime', ''))
                    if e_dt:
                        from datetime import timedelta
                        ist_dt = e_dt + timedelta(hours=5, minutes=30)
                        time_str = f"{ist_dt.strftime('%H:%M')} IST"
                    else:
                        time_str = "Unknown"
                        
                    o_name = war_data.get("opponent", {}).get("name", "Unknown")
                    end_text = (
                        f"🛑 **War Ended!** ({time_str})\n"
                        f"**{clan.name}** vs **{o_name}**\n\n"
                        f"{result_text}\n"
                        f"🛡️ **{clan.name}**: {clan_stars} ⭐ ({clan_dest:.1f}%)\n"
                        f"🏴 **{o_name}**: {opp_stars} ⭐ ({opp_dest:.1f}%)"
                    )
                    
                    if war_notif:
                        await context.bot.send_message(chat_id=chat_id, text=end_text, parse_mode='Markdown')
                    print(f"Log: War ended against {o_name}", flush=True)
                    
                    data["last_war_opponent"] = ""
                    changes_detected = True
                    
            elif state == "notInWar":
                # Clear war attack tracking when not in war
                if "last_war_attacks" in data:
                    data.pop("last_war_attacks")
                    changes_detected = True

                if data.get("last_war_opponent", "") != "":
                    data["last_war_opponent"] = ""
                    changes_detected = True

        # Update stored data if anything changed
        if prev_tags != curr_tags or changes_detected:
            data["members"] = {t: {"name": m.name, "role": str(m.role)} for t, m in current_members.items()}
            _save_data(data)

        print(f"--- [Job] Scan Complete. Found {len(current_members)} members. ---", flush=True)

    except Exception as e:
        logging.error(f"Tracking job error: {e}")


# ── Commands ─────────────────────────────────────────────────────────────────

async def track_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start tracking a clan: /clantrack <clan_tag>"""
    user_id = update.effective_user.id
    if OWNER_ID != 0 and user_id != OWNER_ID:
        await update.message.reply_text("❌ This command is available for the owner only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /clantrack <clan_tag>")
        return

    coc_client = context.bot_data.get("coc_client")
    if not coc_client:
        await update.message.reply_text("❌ CoC API is not connected. Check COC_EMAIL / COC_PASSWORD in .env.")
        return

    new_tag = context.args[0].upper()
    if not new_tag.startswith("#"):
        new_tag = "#" + new_tag

    try:
        clan = await coc_client.get_clan(new_tag)

        data = {
            "tracked_tag": new_tag,
            "members": {m.tag: {"name": m.name, "role": str(m.role)} for m in clan.members},
            "initiated_by": update.effective_user.first_name,
            "chat_id": str(update.effective_chat.id),
            "notifications": DEFAULT_NOTIFICATIONS.copy()
        }
        _save_data(data)

        # Cache chat_id in bot_data for the maintenance notifier
        context.bot_data["tracking_chat_id"] = str(update.effective_chat.id)

        text = (
            f"✅ Now tracking *{clan.name}* (`{new_tag}`)\n\n"
            f"🔔 *Notification Settings:*\n"
            f"Use the buttons below to toggle what you receive."
        )
        await update.message.reply_text(
            text, parse_mode='Markdown',
            reply_markup=_track_config_markup(data)
        )
        print(f"Owner ({update.effective_user.first_name}) started tracking: {new_tag}", flush=True)
    except Exception as e:
        await update.message.reply_text(f"❌ Error finding clan: {e}")


async def deltrack_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop tracking the current clan: /deltrack"""
    user_id = update.effective_user.id
    if OWNER_ID != 0 and user_id != OWNER_ID:
        await update.message.reply_text("❌ This command is available for the owner only.")
        return

    data = {"tracked_tag": None, "members": {}, "initiated_by": "System"}
    _save_data(data)

    await update.message.reply_text(
        f"🛑 Tracking stopped by {update.effective_user.first_name}."
    )


async def crnttrack_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the currently tracked clan: /crnttrack"""
    data = _load_data()
    tag = data.get("tracked_tag")
    if not tag:
        await update.message.reply_text("No clan is currently being tracked. Use /track <clan_tag>.")
        return

    coc_client = context.bot_data.get("coc_client")
    if not coc_client:
        await update.message.reply_text("❌ CoC API is not connected.")
        return

    try:
        clan = await coc_client.get_clan(tag)
        initiator = data.get("initiated_by", "System")

        prefs = _get_notif_prefs(data)
        jl_status = "✅" if prefs.get("join_leave", True) else "❌"
        war_status = "✅" if prefs.get("war", True) else "❌"

        text = (
            f"🛡️ *Currently Tracked Clan*\n\n"
            f"🏷️ *Name:* {clan.name}\n"
            f"📎 *Tag:* {clan.tag}\n"
            f"📝 *Bio:* {clan.description or 'No bio available'}\n\n"
            f"👤 *Tracking initiated by:* {initiator}\n\n"
            f"🔔 *Notifications:*\n"
            f"{jl_status} Join/Leave  |  {war_status} War"
        )

        markup = _track_config_markup(data)

        if clan.badge:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=clan.badge.url,
                caption=text,
                parse_mode='Markdown',
                reply_markup=markup
            )
        else:
            await update.message.reply_text(text, parse_mode='Markdown', reply_markup=markup)

    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching clan details: {e}")


async def track_config_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle notification toggle button presses."""
    query = update.callback_query
    user_id = query.from_user.id
    if OWNER_ID != 0 and user_id != OWNER_ID:
        await query.answer("❌ Only the owner can change tracking settings.", show_alert=True)
        return

    await query.answer()
    action = query.data.split(":", 1)[1]  # tkcfg:join_leave / tkcfg:war / tkcfg:all

    data = _load_data()
    if not data.get("tracked_tag"):
        await query.answer("No clan is being tracked.", show_alert=True)
        return

    prefs = data.get("notifications", DEFAULT_NOTIFICATIONS.copy())

    if action == "all":
        all_on = prefs.get("join_leave", True) and prefs.get("war", True)
        new_val = not all_on  # Toggle: if all on -> all off, else all on
        prefs["join_leave"] = new_val
        prefs["war"] = new_val
    elif action in ("join_leave", "war"):
        prefs[action] = not prefs.get(action, True)

    data["notifications"] = prefs
    _save_data(data)

    markup = _track_config_markup(data)

    # Update the message with new button states
    try:
        if query.message.photo:
            await query.edit_message_reply_markup(reply_markup=markup)
        else:
            await query.edit_message_reply_markup(reply_markup=markup)
    except Exception:
        pass


async def getid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to get current user's ID."""
    await update.message.reply_text(f"Your Telegram ID is: `{update.effective_user.id}`", parse_mode='Markdown')

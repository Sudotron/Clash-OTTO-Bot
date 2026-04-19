"""
Clan Tracking Commands — ported from Req and Leave bot.

Commands:
  /track <clan_tag>    — Start tracking a clan for join/leave/promotion events
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
from telegram import Update
from telegram.ext import ContextTypes

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

    coc_client = coc.Client()
    try:
        await coc_client.login(email, password)
        app.bot_data["coc_client"] = coc_client
        logging.info("Successfully logged into Clash of Clans API.")
    except Exception as e:
        logging.error(f"COC Login Error: {e}")


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

    try:
        print(f"--- [Job] Starting Clan Scan for {clan_tag} ---", flush=True)
        clan = await coc_client.get_clan(clan_tag)
        current_members = {m.tag: m for m in clan.members}

        # First run: just save members and return
        if "members" not in data or not data["members"]:
            data["members"] = {t: {"name": m.name, "role": str(m.role)} for t, m in current_members.items()}
            _save_data(data)
            print(f"First run for {clan_tag}: Saved {len(current_members)} members.", flush=True)
            return

        previous_members = data["members"]
        prev_tags = set(previous_members.keys())
        curr_tags = set(current_members.keys())

        # 1. Detect members who LEFT
        for tag in (prev_tags - curr_tags):
            name = previous_members[tag]["name"]
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

        # Update stored data if anything changed
        if prev_tags != curr_tags or changes_detected:
            data["members"] = {t: {"name": m.name, "role": str(m.role)} for t, m in current_members.items()}
            _save_data(data)

        print(f"--- [Job] Scan Complete. Found {len(current_members)} members. ---", flush=True)

    except Exception as e:
        logging.error(f"Tracking job error: {e}")


# ── Commands ─────────────────────────────────────────────────────────────────

async def track_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start tracking a clan: /track <clan_tag>"""
    user_id = update.effective_user.id
    if OWNER_ID != 0 and user_id != OWNER_ID:
        await update.message.reply_text("❌ This command is available for the owner only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /track <clan_tag>")
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
            "chat_id": str(update.effective_chat.id)
        }
        _save_data(data)

        await update.message.reply_text(
            f"✅ Now tracking join/leave for *{clan.name}* (`{new_tag}`)",
            parse_mode='Markdown'
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

        text = (
            f"🛡️ *Currently Tracked Clan*\n\n"
            f"🏷️ *Name:* {clan.name}\n"
            f"📎 *Tag:* {clan.tag}\n"
            f"📝 *Bio:* {clan.description or 'No bio available'}\n\n"
            f"👤 *Tracking initiated by:* {initiator}"
        )

        if clan.badge:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=clan.badge.url,
                caption=text,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(text, parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching clan details: {e}")


async def getid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to get current user's ID."""
    await update.message.reply_text(f"Your Telegram ID is: `{update.effective_user.id}`", parse_mode='Markdown')

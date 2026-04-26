"""
Capital Contribution Monitor — /cap_stats

Shows ranked Capital Gold contributions per member for the current season.
Paginated output with 10 members per page.
"""

import os
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from coc_api import get_clan, get_player, get_player_stats, get_clan_capital_raid_seasons
from commands.utils import E, _resolve_tag, fmt_number, current_season

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
MEMBERS_PER_PAGE = 10


async def _fetch_member_capital_stats(tag: str, season: str) -> dict:
    """Fetch capital stats for a single member. Returns dict with donated/raided."""
    stats = await get_player_stats(tag)
    if isinstance(stats, dict) and "error" not in stats:
        capital = stats.get("capital", {})
        season_data = capital.get(season, {}) if capital else {}
        return {
            "donated": season_data.get("donated", 0),
            "raided": season_data.get("raided", 0),
        }

    # Fallback: fetch player data and use achievements for all-time values
    player = await get_player(tag)
    if isinstance(player, dict) and "error" not in player:
        ach = {a["name"]: a["value"] for a in player.get("achievements", [])}
        return {
            "donated": ach.get("Most Valuable Clanmate", 0),
            "raided": ach.get("Aggressive Capitalism", 0),
            "all_time": True,
        }

    return {"donated": 0, "raided": 0, "error": True}


def _build_cap_page(member_stats: list, clan_name: str, data_label: str, total: int, page: int, clan_tag: str) -> tuple:
    """Build a single page of cap_stats output."""
    contributors = [m for m in member_stats if m["donated"] > 0]
    zero_donors = [m for m in member_stats if m["donated"] == 0]
    total_pages = max(1, -(-len(contributors) // MEMBERS_PER_PAGE))  # ceil division

    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0

    start = page * MEMBERS_PER_PAGE
    end = start + MEMBERS_PER_PAGE
    page_members = contributors[start:end]

    medals = ["🥇", "🥈", "🥉"]

    text = (
        f"💰 **Capital Gold Stats — {clan_name}**\n"
        f"📅 {data_label} | 👥 {total} members\n"
        f"{'─' * 30}\n\n"
    )

    if page_members:
        for i, m in enumerate(page_members):
            rank = start + i
            medal = medals[rank] if rank < 3 else f"`{rank + 1}.`"
            clean_tag = m["tag"].replace("#", "")
            plink = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag=%23{clean_tag}"
            text += (
                f"{medal} [{m['name']}]({plink})\n"
                f"   💰 Donated: {fmt_number(m['donated'])} | 🗡️ Raided: {fmt_number(m['raided'])}\n"
            )
    else:
        text += "⚠️ **No contributions recorded.**\n"

    # Show zero donors on the last page
    if page == total_pages - 1 and zero_donors:
        text += f"\n{'─' * 30}\n"
        text += f"⚠️ **Zero Contributions ({len(zero_donors)}):**\n"
        zero_names = [m["name"] for m in zero_donors]
        if len(zero_names) > 15:
            text += ", ".join(zero_names[:15]) + f"... (+{len(zero_names) - 15} more)"
        else:
            text += ", ".join(zero_names)
        text += "\n"

    text += f"\n📄 Page {page + 1}/{total_pages}"

    # Build navigation buttons
    norm_tag = clan_tag.replace("#", "")
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"capst:{page - 1}:{norm_tag}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"capst:{page + 1}:{norm_tag}"))

    keyboard = [buttons] if buttons else []
    return text, InlineKeyboardMarkup(keyboard) if keyboard else None


async def cap_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command: /cap_stats [clan_tag] — Show Capital Gold contribution rankings."""
    tag = await _resolve_tag(update, context, entity_type="clan")
    if not tag:
        await update.message.reply_text(
            "Please provide a clan tag or link an account first.\n"
            "Usage: `/cap_stats #CLANTAG`",
            parse_mode="Markdown",
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = await update.message.reply_text("⏳ Gathering Capital Gold contributions... This may take a moment.")

    # Resolve player tag to clan tag if needed
    clan_data = await get_clan(tag)
    if "error" in clan_data:
        pdata = await get_player(tag)
        if "error" not in pdata and pdata.get("clan"):
            clan_data = await get_clan(pdata["clan"]["tag"])
        if "error" in clan_data:
            await msg.edit_text(f"❌ Could not find clan: {clan_data.get('error', 'Unknown error')}")
            return

    clan_name = clan_data.get("name", "Unknown")
    clan_tag = clan_data.get("tag", tag)
    members = clan_data.get("memberList", [])
    season = current_season()

    if not members:
        await msg.edit_text("❌ No members found in the clan.")
        return

    # Fetch stats for all members in parallel (batches of 10)
    results = {}
    batch_size = 10
    member_tags = [m.get("tag", "") for m in members]

    for i in range(0, len(member_tags), batch_size):
        batch = member_tags[i : i + batch_size]
        tasks = [_fetch_member_capital_stats(t, season) for t in batch]
        batch_results = await asyncio.gather(*tasks)
        for t, r in zip(batch, batch_results):
            results[t] = r

    # Build member stats list
    member_stats = []
    for m in members:
        mtag = m.get("tag", "")
        mname = m.get("name", "Unknown")
        stats = results.get(mtag, {"donated": 0, "raided": 0})
        member_stats.append({
            "name": mname,
            "tag": mtag,
            "donated": stats.get("donated", 0),
            "raided": stats.get("raided", 0),
            "all_time": stats.get("all_time", False),
        })

    # Sort by donated descending
    member_stats.sort(key=lambda x: x["donated"], reverse=True)

    is_all_time = any(m.get("all_time") for m in member_stats)
    data_label = "All-Time" if is_all_time else f"Season {season}"

    # Store for pagination callbacks
    norm_tag = clan_tag.replace("#", "")
    context.bot_data[f"capst_{norm_tag}"] = {
        "stats": member_stats,
        "clan_name": clan_name,
        "data_label": data_label,
        "total": len(members),
        "clan_tag": clan_tag,
    }

    text, markup = _build_cap_page(member_stats, clan_name, data_label, len(members), 0, clan_tag)
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)


async def cap_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle cap_stats pagination button presses."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 2)
    page = int(parts[1])
    norm_tag = parts[2]

    cached = context.bot_data.get(f"capst_{norm_tag}")
    if not cached:
        await query.edit_message_text("❌ Session expired. Please run /cap_stats again.")
        return

    text, markup = _build_cap_page(
        cached["stats"], cached["clan_name"], cached["data_label"],
        cached["total"], page, cached["clan_tag"]
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)

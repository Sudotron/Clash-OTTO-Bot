import asyncio
import os
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from coc_api import (
    get_clan, get_player, get_clan_war, get_previous_wars,
    get_cwl_group, get_cwl_war, search_clans
)
from collections import Counter
from commands.utils import E, _resolve_tag, _build_clan_page1, _build_members_page

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

async def clan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context, entity_type='clan')
    if not tag:
        await update.message.reply_text("Please provide a clan tag or link a player account first.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    loading = await update.message.reply_text("⏳ Scouring the battlefields for clan data...")
    
    data = await get_clan(tag)
    if "error" in data:
        pdata = await get_player(tag)
        if "error" not in pdata and pdata.get('clan'):
            data = await get_clan(pdata['clan']['tag'])
        if "error" in data:
            await loading.edit_text("❌ Could not find clan details. Is it a valid clan tag?")
            return

    norm_tag = data.get('tag', tag).strip().upper()
    context.bot_data[f"cdata_{norm_tag}"] = data

    page1_text = _build_clan_page1(data)
    keyboard = [[InlineKeyboardButton("👥 Members List", callback_data=f"clan_p2:{norm_tag}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    badge_url = data.get('badgeUrls', {}).get('large', '')

    await loading.delete()
    if badge_url:
        await update.message.reply_photo(
            photo=badge_url, caption=page1_text, parse_mode='Markdown', reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(page1_text, parse_mode='Markdown', reply_markup=reply_markup, disable_web_page_preview=True)


async def clan_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "clan_noop":
        await query.answer()
        return

    await query.answer()
    parts    = query.data.split(":", 2)
    action   = parts[0]
    tag      = parts[1] if len(parts) > 1 else ""
    page_str = parts[2] if len(parts) > 2 else "0"
    norm_tag = tag.strip().upper()

    try:
        page = int(page_str)
    except ValueError:
        page = 0

    data = context.bot_data.get(f"cdata_{norm_tag}")
    if not data:
        data = await get_clan(norm_tag)
        if "error" in data:
            await query.edit_message_caption(caption=f"❌ {data['error']}")
            return
        context.bot_data[f"cdata_{norm_tag}"] = data

    if action == "clan_p1":
        page1_text = _build_clan_page1(data)
        keyboard   = [[InlineKeyboardButton("👥 Members List", callback_data=f"clan_p2:{norm_tag}")]]
        await query.edit_message_caption(
            caption=page1_text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif action == "clan_p2":
        text, markup = _build_members_page(data, 0)
        await query.edit_message_caption(
            caption=text, parse_mode='Markdown', reply_markup=markup
        )
    elif action == "clan_members":
        text, markup = _build_members_page(data, page)
        await query.edit_message_caption(
            caption=text, parse_mode='Markdown', reply_markup=markup
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _th_roster(members: list) -> str:
    """Build TH breakdown from war members list, e.g. 'TH16×5 | TH15×8'."""
    if not members:
        return ""
    th_counts = Counter(m.get('townhallLevel', 0) for m in members)
    parts = [f"TH{th}×{count}" for th, count in sorted(th_counts.items(), reverse=True) if th > 0]
    return "  " + " | ".join(parts) if parts else ""



def _parse_coc_time(ts: str) -> datetime | None:
    """Parse CoC API timestamp '20250501T120000.000Z' -> UTC datetime."""
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _fmt_remaining(dt: datetime | None, state: str) -> str:
    """Return a human-readable time remaining string, or empty string."""
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    diff = dt - now
    total_sec = int(diff.total_seconds())
    if total_sec <= 0:
        return ""
    hours, rem = divmod(total_sec, 3600)
    minutes = rem // 60
    if hours >= 24:
        days = hours // 24
        t_str = f"{days}d {hours % 24}h"
    else:
        t_str = f"{hours}h {minutes}m"
        
    if state == 'preparation':
        return f"\n⏳ Preparation time left: *{t_str}*"
    else:
        return f"\n⏰ Remaining time: *{t_str}*"


def _attack_progress(war_data: dict) -> str:
    """Return attack count bar e.g. ⚔️ Attacks: 24/30."""
    team_size = war_data.get('teamSize', 0) or 0
    attacks_per = war_data.get('attacksPerMember', 2)
    total_possible = team_size * attacks_per
    members = war_data.get('clan', {}).get('members', [])
    used = sum(len(m.get('attacks', [])) for m in members)
    bar_filled = int((used / total_possible) * 10) if total_possible else 0
    bar = '█' * bar_filled + '░' * (10 - bar_filled)
    return f"\n⚔️ Attacks: `{used}/{total_possible}` [{bar}]"


async def clanwar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context, entity_type='clan')
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = await update.message.reply_text("⏳ Diving into the game for war log details...")

    war_data = await get_clan_war(tag)
    
    if "error" in war_data:
        clan_data = await get_clan(tag)
        
        if "error" in clan_data:
            pdata = await get_player(tag)
            if "error" not in pdata and pdata.get('clan'):
                clan_data = await get_clan(pdata['clan']['tag'])
                war_data = await get_clan_war(pdata['clan']['tag'])
        
        if "error" not in clan_data:
            if not clan_data.get('isWarLogPublic', False):
                badge_url = clan_data.get('badgeUrls', {}).get('large', '')
                desc = clan_data.get('description', 'No description.')
                clean_tag = clan_data.get('tag', tag).replace('#', '')
                link = f"https://link.clashofclans.com/en?action=OpenClanProfile&tag=%23{clean_tag}"
                
                text = (
                    f"🛡️ **{clan_data.get('name', 'Clan')}** `#{clean_tag}`\n\n"
                    f"📖 *{desc}*\n\n"
                    f"🔗 [Open in Clash of Clans]({link})\n\n"
                    f"⚠️ **THE CLAN WAR LOG IS PRIVATE**"
                )
                await msg.delete()
                if badge_url:
                    await update.message.reply_photo(photo=badge_url, caption=text, parse_mode='Markdown')
                else:
                    await update.message.reply_text(text, parse_mode='Markdown', disable_web_page_preview=True)
                return
        
        if "error" in war_data:
            await msg.edit_text(
                f"❌ Could not find war details.\nReason: _{war_data.get('error')}_\n"
                "*(If you just made your log public, Clash API may take a few minutes to update its cache!)*",
                parse_mode='Markdown'
            )
            return

    norm_tag = war_data.get('clan', {}).get('tag', tag).strip().upper()
    
    state = war_data.get('state')
    if state == 'notInWar':
        prev_wars = await get_previous_wars(norm_tag, limit=2)
        items = prev_wars.get('items', [])
        
        if not items:
            await msg.edit_text("⚔️ The clan is not currently in a standard war (or is in CWL) and no previous war data was found.")
            return
            
        text = f"⚔️ **Clan is not in war. Displaying last {len(items)} wars:**\n\n"
        keyboard = []
        for i, w in enumerate(items):
            wn = w.get('clan', {}).get('name', 'Clan')
            on = w.get('opponent', {}).get('name', 'Opponent')
            ws = w.get('clan', {}).get('stars', 0)
            os_ = w.get('opponent', {}).get('stars', 0)
            res = "🏆 Victory" if ws > os_ else "💀 Defeat" if os_ > ws else "🤝 Draw"
            
            text += f"**War {i+1}: {wn} vs {on}**\n"
            text += f"{res} | ⭐ {ws} — {os_}\n\n"
            keyboard.append([InlineKeyboardButton(f"📊 War {i+1} Analytics", callback_data=f"cwar_a:home:{norm_tag}:{i}:0")])
            
        await msg.edit_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
        return

    clan_name  = war_data.get('clan', {}).get('name', 'Unknown')
    clan_stars = war_data.get('clan', {}).get('stars', 0)
    clan_dest  = war_data.get('clan', {}).get('destructionPercentage', 0)
    opp_name   = war_data.get('opponent', {}).get('name', 'Unknown')
    opp_stars  = war_data.get('opponent', {}).get('stars', 0)
    opp_dest   = war_data.get('opponent', {}).get('destructionPercentage', 0)
    team_size  = war_data.get('teamSize', '?')

    # ── Time remaining ──
    if state == 'preparation':
        start_dt = _parse_coc_time(war_data.get('startTime', ''))
        time_str = _fmt_remaining(start_dt, "preparation")
        state_label = "⚙️ Preparation"
    elif state == 'inWar':
        end_dt = _parse_coc_time(war_data.get('endTime', ''))
        time_str = _fmt_remaining(end_dt, "inWar")
        state_label = "🔥 In War"
    elif state == 'warEnded':
        end_dt = _parse_coc_time(war_data.get('endTime', ''))
        if end_dt:
            ist_dt = end_dt + timedelta(hours=5, minutes=30)
            time_str = f"\n⏰ War ended at: *{ist_dt.strftime('%H:%M')} IST*"
        else:
            time_str = "\n⏰ War ended"
        state_label = "War Ended"
    else:
        time_str = ""
        state_label = state.capitalize() if state else "Unknown"

    # ── Determine result if war ended ──
    if state == 'warEnded':
        if clan_stars > opp_stars:
            result_line = "\n🏆 **Result: VICTORY!**"
        elif opp_stars > clan_stars:
            result_line = "\n💀 **Result: DEFEAT**"
        else:
            if clan_dest > opp_dest:
                result_line = "\n🏆 **Result: VICTORY! (Destruction tiebreak)**"
            elif opp_dest > clan_dest:
                result_line = "\n💀 **Result: DEFEAT (Destruction tiebreak)**"
            else:
                result_line = "\n🤝 **Result: DRAW**"
    else:
        result_line = ""

    # ── TH Roster ──
    clan_members_list = war_data.get('clan', {}).get('members', [])
    opp_members_list = war_data.get('opponent', {}).get('members', [])
    clan_roster = _th_roster(clan_members_list)
    opp_roster = _th_roster(opp_members_list)

    text = (
        f"⚔️ **Clan War — {state_label}**\n"
        f"👥 Size: {team_size}v{team_size}"
        f"{time_str}"
        f"{result_line}\n"
        f"{'─' * 30}\n"
        f"🛡️ **{clan_name}**\n"
        f"  ⭐ Stars: {clan_stars}   💥 Dest: {clan_dest:.1f}%\n"
        f"{clan_roster}\n\n"
        f"🏴 **{opp_name}**\n"
        f"  ⭐ Stars: {opp_stars}   💥 Dest: {opp_dest:.1f}%\n"
        f"{opp_roster}\n"
    )
    
    keyboard = [[
        InlineKeyboardButton("📊 Analytics", callback_data=f"cwar_a:home:{norm_tag}:live:0"),
        InlineKeyboardButton("🗡️ Attacks", callback_data=f"cwar_a:attacks:{norm_tag}:live:0")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await msg.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup, disable_web_page_preview=True)


def _cwar_analytics_markup(view: str, tag: str, war_index: str, current_page: int, total_pages: int):
    nav_row = []
    if current_page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"cwar_a:{view}:{tag}:{war_index}:{current_page-1}"))
    if current_page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"cwar_a:{view}:{tag}:{war_index}:{current_page+1}"))
        
    keyboard = []
    if nav_row:
        keyboard.append(nav_row)
        
    act_tag = tag.strip().upper()
    keyboard.extend([
        [
            InlineKeyboardButton("❌ Missed", callback_data=f"cwar_a:missed:{act_tag}:{war_index}:0"),
            InlineKeyboardButton("🌟 3-Stars", callback_data=f"cwar_a:3star:{act_tag}:{war_index}:0"),
            InlineKeyboardButton("⭐ Stars", callback_data=f"cwar_a:stars:{act_tag}:{war_index}:0")
        ],
        [
            InlineKeyboardButton("🗡️ All Attacks", callback_data=f"cwar_a:attacks:{act_tag}:{war_index}:0"),
            InlineKeyboardButton("◀️ War Overview", callback_data=f"cwar_a:home:{act_tag}:{war_index}:0")
        ]
    ])
    return InlineKeyboardMarkup(keyboard)

async def clanwar_analytics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    # cwar_a:view:tag:war_index:page
    view = parts[1]
    tag = parts[2]
    norm_tag = tag.upper()
    war_index = parts[3] if len(parts) > 3 else "live"
    page = int(parts[4]) if len(parts) > 4 else 0

    if war_index == "live":
        war_data = await get_clan_war(norm_tag)
    else:
        prev_wars = await get_previous_wars(norm_tag, limit=2)
        idx = int(war_index)
        items = prev_wars.get('items', [])
        if len(items) > idx:
            war_data = items[idx]
        else:
            war_data = {"error": "War not found."}

    if "error" in war_data:
        await query.edit_message_text(f"❌ Failed to fetch data: {war_data['error']}")
        return

    if view == "home":
        state = war_data.get('state', 'Unknown')
        clan_name = war_data.get('clan', {}).get('name', 'Unknown')
        clan_stars = war_data.get('clan', {}).get('stars', 0)
        clan_dest = war_data.get('clan', {}).get('destructionPercentage', 0)
        opp_name = war_data.get('opponent', {}).get('name', 'Unknown')
        opp_stars = war_data.get('opponent', {}).get('stars', 0)
        opp_dest = war_data.get('opponent', {}).get('destructionPercentage', 0)
        team_size = war_data.get('teamSize', '?')
        c_roster = _th_roster(war_data.get('clan', {}).get('members', []))
        o_roster = _th_roster(war_data.get('opponent', {}).get('members', []))

        text = (
            f"⚔️ **Clan War — {state.capitalize() if state else 'Unknown'}**\n"
            f"👥 Size: {team_size}v{team_size}\n\n"
            f"🛡️ **{clan_name}**\n"
            f"  ⭐ Stars: {clan_stars}   💥 Dest: {clan_dest:.1f}%\n"
            f"{c_roster}\n\n"
            f"🏴 **{opp_name}**\n"
            f"  ⭐ Stars: {opp_stars}   💥 Dest: {opp_dest:.1f}%\n"
            f"{o_roster}\n"
        )
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=_cwar_analytics_markup(view, norm_tag, war_index, 0, 1), disable_web_page_preview=True)
        return

    members = war_data.get('clan', {}).get('members', [])
    attacks_per_member = war_data.get('attacksPerMember', 2)
    
    lines = []
    
    if view == "missed":
        lines.append(f"📊 **War Analytics — Missed Attacks**\n{'─'*28}\n")
        missed = []
        for m in members:
            atk_count = len(m.get('attacks', []))
            if atk_count < attacks_per_member:
                count = attacks_per_member - atk_count
                ptag = m.get('tag', '').strip('#')
                plink = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={ptag}"
                missed.append(f"• {m.get('name')} (TH{m.get('townhallLevel', '?')}) [#{ptag}]({plink}) — {count} missed")
        if not missed:
            lines.append("✅ **All attacks have been used!**")
        else:
            lines.extend(missed)

    elif view == "3star":
        lines.append(f"📊 **War Analytics — 🌟 3-Star Specialists**\n{'─'*28}\n")
        stars = []
        for m in members:
            for atk in m.get('attacks', []):
                if atk.get('stars', 0) == 3:
                    ptag = m.get('tag', '').strip('#')
                    plink = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={ptag}"
                    stars.append(f"• {m.get('name')} (TH{m.get('townhallLevel', '?')}) [#{ptag}]({plink})")
        if not stars:
            lines.append("❌ **No 3-star attacks.**")
        else:
            lines.extend(stars)

    elif view == "stars":
        lines.append(f"📊 **War Analytics — ⭐ Other Attacks**\n{'─'*28}\n")
        stars = []
        for m in members:
            for atk in m.get('attacks', []):
                st = atk.get('stars', 0)
                if st < 3:
                    ptag = m.get('tag', '').strip('#')
                    plink = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={ptag}"
                    stars.append(f"• {m.get('name')} (TH{m.get('townhallLevel', '?')}) [#{ptag}]({plink}) — {st}⭐ ({atk.get('destructionPercentage', 0)}%)")
        if not stars:
            lines.append("❌ **No 2-Star or lower attacks.**")
        else:
            lines.extend(stars)

    elif view == "attacks":
        lines.append(f"🗡️ **War Analytics — All Attacks**\n{'─'*28}\n")
        all_attacks_raw = []
        all_members = war_data.get('clan', {}).get('members', []) + war_data.get('opponent', {}).get('members', [])
        member_map = {m.get('tag', ''): m for m in all_members}
        
        for m in war_data.get('clan', {}).get('members', []):
            mname = m.get('name', 'Unknown')
            mth   = m.get('townhallLevel', '?')
            for atk in m.get('attacks', []):
                defender = member_map.get(atk.get('defenderTag', ''), {})
                dname = defender.get('name', 'Unknown')
                dth   = defender.get('townhallLevel', '?')
                st    = atk.get('stars', 0)
                dest  = atk.get('destructionPercentage', 0)
                order = atk.get('order', 999)
                stars_str = '⭐' * st if st > 0 else '☆'
                all_attacks_raw.append((order, f"`{order}.` {mname}(Th{mth}) ─────> {dname}(Th{dth}) {stars_str} ({dest}%)"))
                
        for o in war_data.get('opponent', {}).get('members', []):
            oname = o.get('name', 'Unknown')
            oth   = o.get('townhallLevel', '?')
            for atk in o.get('attacks', []):
                defender = member_map.get(atk.get('defenderTag', ''), {})
                dname = defender.get('name', 'Unknown')
                dth   = defender.get('townhallLevel', '?')
                st    = atk.get('stars', 0)
                dest  = atk.get('destructionPercentage', 0)
                order = atk.get('order', 999)
                stars_str = '⭐' * st if st > 0 else '☆'
                all_attacks_raw.append((order, f"`{order}.` {dname}(Th{dth}) <───── {oname}(Th{oth}) {stars_str} ({dest}%)"))

        all_attacks_raw.sort(key=lambda x: x[0])
        all_attacks = [x[1] for x in all_attacks_raw]

        if not all_attacks:
            lines.append("❌ No attacks recorded yet.")
        else:
            lines.extend(all_attacks)

    chunks = []
    cur = ""
    for ln in lines:
        if len(cur) + len(ln) > 3800:
            chunks.append(cur)
            cur = ln + "\n"
        else:
            cur += ln + "\n"
    if cur: chunks.append(cur)
    
    total_pages = len(chunks) if chunks else 1
    safe_page = min(page, total_pages - 1)
    
    text = chunks[safe_page] if chunks else "No data."
    if total_pages > 1:
        text += f"\n_Page {safe_page + 1} of {total_pages}_"
        
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=_cwar_analytics_markup(view, norm_tag, war_index, safe_page, total_pages), disable_web_page_preview=True)


def _clansorted_markup(tag: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏆 Trophies", callback_data=f"clansort:trophies:{tag}"),
            InlineKeyboardButton("🏯 Town Hall", callback_data=f"clansort:th:{tag}"),
            InlineKeyboardButton("🔼 Donations", callback_data=f"clansort:donations:{tag}")
        ],
        [
            InlineKeyboardButton("👑 Role", callback_data=f"clansort:role:{tag}"),
            InlineKeyboardButton("🎖️ XP Level", callback_data=f"clansort:xplevel:{tag}")
        ]
    ])

async def clansorted_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context, entity_type='clan')
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    norm_tag = tag.strip().upper()
    text = "📊 **Clan Members Sorting**\nHow would you like to sort the clan members?"
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=_clansorted_markup(norm_tag))


async def clansorted_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 2)
    sort_type = parts[1]
    tag = parts[2] if len(parts) > 2 else ""
    norm_tag = tag.strip().upper()

    data = context.bot_data.get(f"cdata_{norm_tag}")
    if not data:
        data = await get_clan(norm_tag)
        if "error" in data:
            pdata = await get_player(norm_tag)
            if "error" not in pdata and pdata.get('clan'):
                data = await get_clan(pdata['clan']['tag'])
            if "error" in data:
                await query.edit_message_text(f"❌ {data['error']}", reply_markup=_clansorted_markup(norm_tag))
                return
        context.bot_data[f"cdata_{norm_tag}"] = data

    clan_name = data.get('name', 'Unknown')
    members = data.get('memberList', [])

    # Perform Sorting
    if sort_type == "trophies":
        members = sorted(members, key=lambda x: x.get('trophies', 0), reverse=True)
        sort_title = "🏆 Trophies"
        def format_val(m): return f"🏆 {m.get('trophies', 0):,}"
    elif sort_type == "th":
        members = sorted(members, key=lambda x: x.get('townHallLevel', 0), reverse=True)
        sort_title = "🏯 Town Hall"
        def format_val(m): return f"TH{m.get('townHallLevel', '?')}"
    elif sort_type == "donations":
        members = sorted(members, key=lambda x: x.get('donations', 0), reverse=True)
        sort_title = "🔼 Donations"
        def format_val(m): return f"🔼 {m.get('donations', 0):,} / 🔽 {m.get('donationsReceived', 0):,}"
    elif sort_type == "role":
        role_map = {"leader": 4, "coLeader": 3, "admin": 2, "member": 1}
        members = sorted(members, key=lambda x: role_map.get(x.get('role', 'member'), 0), reverse=True)
        sort_title = "👑 Role"
        def format_val(m): return f"Role: {m.get('role', 'member').capitalize()}"
    elif sort_type == "xplevel":
        members = sorted(members, key=lambda x: x.get('expLevel', 0), reverse=True)
        sort_title = "🎖️ XP Level"
        def format_val(m): return f"Lvl {m.get('expLevel', 0)}"
    else:
        members = sorted(members, key=lambda x: x.get('clanRank', 99))
        sort_title = "Rank"
        def format_val(m): return f"Rank #{m.get('clanRank')}"

    text = f"👥 *{clan_name} — Sorted by {sort_title}*\n{'─' * 28}\n"
    for i, m in enumerate(members[:50]): # Top 50 
        mname = m.get('name', 'Unknown')
        text += f"`{i+1}.` {mname} — {format_val(m)}\n"

    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=_clansorted_markup(norm_tag))


# ═══════════════════════════════════════════════════════════════════════════════
# /cwl — Clan War League
# ═══════════════════════════════════════════════════════════════════════════════

def _cwl_round_markup(tag: str, round_idx: int, total_rounds: int, view: str = "round") -> InlineKeyboardMarkup:
    """Navigation keyboard for CWL rounds."""
    nav = []
    if round_idx > 0:
        nav.append(InlineKeyboardButton("◀️ Prev Round", callback_data=f"cwl_r:{view}:{tag}:{round_idx - 1}"))
    if round_idx < total_rounds - 1:
        nav.append(InlineKeyboardButton("Next Round ▶️", callback_data=f"cwl_r:{view}:{tag}:{round_idx + 1}"))
    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([
        InlineKeyboardButton("📋 Group Overview", callback_data=f"cwl_r:overview:{tag}:0"),
        InlineKeyboardButton("🗡️ Attacks", callback_data=f"cwl_r:attacks:{tag}:{round_idx}"),
    ])
    return InlineKeyboardMarkup(keyboard)


def _cwl_overview_text(group: dict, clan_tag: str) -> str:
    """Build CWL group overview: season, participating clans, round info."""
    season = group.get('season', 'Unknown Season')
    clans  = group.get('clans', [])
    rounds = group.get('rounds', [])
    total_rounds = len(rounds)
    completed = sum(1 for r in rounds if any(wt != "#0" for wt in r.get('warTags', [])))

    text = (
        f"🌟 **Clan War League — {season}**\n"
        f"{'─' * 30}\n"
        f"📅 Rounds: {completed}/{total_rounds} completed\n"
        f"👥 Participating Clans ({len(clans)}):\n"
    )
    for i, c in enumerate(clans):
        ctag  = c.get('tag', '?')
        cname = c.get('name', 'Unknown')
        clvl  = c.get('clanLevel', '?')
        icon  = "🏆" if ctag.upper() == clan_tag.upper() else "🛡️"
        text += f"  {icon} `{i+1}.` **{cname}** (Lvl {clvl}) `{ctag}`\n"
    return text


async def cwl_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context, entity_type='clan')
    if not tag:
        await update.message.reply_text(
            "Please provide a clan tag or link a clan/player account first.\n"
            "Usage: `/cwl #CLANTAG`", parse_mode='Markdown'
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = await update.message.reply_text("🌟 Fetching CWL group data...")

    # If player tag given, resolve to clan tag
    pdata = await get_player(tag)
    if "error" not in pdata and pdata.get('clan'):
        tag = pdata['clan']['tag']

    norm_tag = tag.strip().upper()
    group = await get_cwl_group(norm_tag)

    if "error" in group:
        await msg.edit_text(
            "❌ CWL data not available.\n\n"
            "_CWL only runs for the first ~10 days of each month. "
            "Outside that window, or if the clan is not participating, no data is returned._",
            parse_mode='Markdown'
        )
        return

    context.bot_data[f"cwl_{norm_tag}"] = group

    overview_text = _cwl_overview_text(group, norm_tag)
    rounds = group.get('rounds', [])
    total_rounds = len(rounds)

    # Find latest active round
    latest = 0
    for i, r in enumerate(rounds):
        if any(wt != "#0" for wt in r.get('warTags', [])):
            latest = i

    keyboard = []
    if total_rounds > 0:
        keyboard.append([InlineKeyboardButton(
            f"⚔️ View Round {latest + 1}",
            callback_data=f"cwl_r:round:{norm_tag}:{latest}"
        )])

    await msg.edit_text(
        overview_text, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        disable_web_page_preview=True
    )


async def cwl_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts     = query.data.split(":", 3)   # cwl_r:view:tag:round_idx
    view      = parts[1] if len(parts) > 1 else "overview"
    tag       = parts[2] if len(parts) > 2 else ""
    norm_tag  = tag.strip().upper()
    round_idx = int(parts[3]) if len(parts) > 3 else 0

    group = context.bot_data.get(f"cwl_{norm_tag}")
    if not group:
        group = await get_cwl_group(norm_tag)
        if "error" in group:
            await query.edit_message_text("❌ CWL data expired. Run `/cwl` again.", parse_mode='Markdown')
            return
        context.bot_data[f"cwl_{norm_tag}"] = group

    rounds       = group.get('rounds', [])
    total_rounds = len(rounds)

    if view == "overview":
        text = _cwl_overview_text(group, norm_tag)
        latest = 0
        for i, r in enumerate(rounds):
            if any(wt != "#0" for wt in r.get('warTags', [])):
                latest = i
        kb = [[InlineKeyboardButton(f"⚔️ View Round {latest + 1}", callback_data=f"cwl_r:round:{norm_tag}:{latest}")]] if total_rounds > 0 else []
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb) if kb else None, disable_web_page_preview=True)
        return

    if round_idx >= total_rounds:
        await query.edit_message_text("❌ Round not found.")
        return

    round_data = rounds[round_idx]
    war_tags   = [wt for wt in round_data.get('warTags', []) if wt != "#0"]

    if not war_tags:
        await query.edit_message_text(
            f"⏳ Round {round_idx + 1} hasn't started yet.",
            reply_markup=_cwl_round_markup(norm_tag, round_idx, total_rounds, view)
        )
        return

    # Find the war that involves our clan
    our_war = None
    for wt in war_tags:
        wdata = await get_cwl_war(wt)
        if "error" not in wdata:
            c_tag = wdata.get('clan', {}).get('tag', '').upper()
            o_tag = wdata.get('opponent', {}).get('tag', '').upper()
            if norm_tag in (c_tag, o_tag):
                if o_tag == norm_tag:
                    wdata['clan'], wdata['opponent'] = wdata['opponent'], wdata['clan']
                our_war = wdata
                break

    if not our_war:
        our_war = await get_cwl_war(war_tags[0])

    if not our_war or "error" in our_war:
        await query.edit_message_text(
            f"❌ Could not load Round {round_idx + 1} war data.",
            reply_markup=_cwl_round_markup(norm_tag, round_idx, total_rounds, view)
        )
        return

    c_name  = our_war.get('clan', {}).get('name', 'Clan')
    c_stars = our_war.get('clan', {}).get('stars', 0)
    c_dest  = our_war.get('clan', {}).get('destructionPercentage', 0)
    o_name  = our_war.get('opponent', {}).get('name', 'Opponent')
    o_stars = our_war.get('opponent', {}).get('stars', 0)
    o_dest  = our_war.get('opponent', {}).get('destructionPercentage', 0)
    w_state = our_war.get('state', 'unknown')
    w_size  = our_war.get('teamSize', '?')

    if w_state == 'preparation':
        s_dt = _parse_coc_time(our_war.get('startTime', ''))
        time_str    = _fmt_remaining(s_dt, "preparation")
        state_label = "⚙️ Preparation"
    elif w_state == 'inWar':
        e_dt = _parse_coc_time(our_war.get('endTime', ''))
        time_str    = _fmt_remaining(e_dt, "inWar")
        state_label = "🔥 In War"
    elif w_state == 'warEnded':
        e_dt = _parse_coc_time(our_war.get('endTime', ''))
        if e_dt:
            ist_dt = e_dt + timedelta(hours=5, minutes=30)
            time_str = f"\n⏰ War ended at: *{ist_dt.strftime('%H:%M')} IST*"
        else:
            time_str = "\n⏰ War ended"
        state_label = "War Ended"
    else:
        time_str    = ""
        state_label = w_state.capitalize()

    if w_state == 'warEnded':
        result_line = f"\n{'🏆 Victory' if c_stars > o_stars else '💀 Defeat' if o_stars > c_stars else '🤝 Draw'}"
    else:
        result_line = ""

    if view == "attacks":
        lines = [f"🗡️ **CWL Round {round_idx + 1} — All Attacks**\n{'─'*28}\n"]
        all_attacks_raw = []
        all_members = our_war.get('clan', {}).get('members', []) + our_war.get('opponent', {}).get('members', [])
        member_map  = {m.get('tag', ''): m for m in all_members}
        
        for m in our_war.get('clan', {}).get('members', []):
            mname = m.get('name', 'Unknown')
            mth   = m.get('townhallLevel', '?')
            for atk in m.get('attacks', []):
                defender = member_map.get(atk.get('defenderTag', ''), {})
                dname = defender.get('name', 'Unknown')
                dth   = defender.get('townhallLevel', '?')
                st    = atk.get('stars', 0)
                dest  = atk.get('destructionPercentage', 0)
                order = atk.get('order', 999)
                stars_str = '⭐' * st if st > 0 else '☆'
                all_attacks_raw.append((order, f"`{order}.` {mname}(Th{mth}) ─────> {dname}(Th{dth}) {stars_str} ({dest}%)"))

        for o in our_war.get('opponent', {}).get('members', []):
            oname = o.get('name', 'Unknown')
            oth   = o.get('townhallLevel', '?')
            for atk in o.get('attacks', []):
                defender = member_map.get(atk.get('defenderTag', ''), {})
                dname = defender.get('name', 'Unknown')
                dth   = defender.get('townhallLevel', '?')
                st    = atk.get('stars', 0)
                dest  = atk.get('destructionPercentage', 0)
                order = atk.get('order', 999)
                stars_str = '⭐' * st if st > 0 else '☆'
                all_attacks_raw.append((order, f"`{order}.` {dname}(Th{dth}) <───── {oname}(Th{oth}) {stars_str} ({dest}%)"))

        all_attacks_raw.sort(key=lambda x: x[0])
        all_attacks = [x[1] for x in all_attacks_raw]

        if not all_attacks:
            lines.append("❌ No attacks recorded for this round yet.")
        else:
            lines.extend(all_attacks)
        text = "\n".join(lines)
    else:
        text = (
            f"🌟 **CWL — Round {round_idx + 1}/{total_rounds}** ({state_label})\n"
            f"👥 {w_size}v{w_size}{time_str}{result_line}\n"
            f"{'─' * 30}\n"
            f"🛡️ **{c_name}**\n"
            f"  ⭐ Stars: {c_stars}   💥 Dest: {c_dest:.1f}%\n\n"
            f"🏴 **{o_name}**\n"
            f"  ⭐ Stars: {o_stars}   💥 Dest: {o_dest:.1f}%\n"
        )

    if len(text) > 4096:
        text = text[:4090] + "\n…"

    await query.edit_message_text(
        text, parse_mode='Markdown',
        reply_markup=_cwl_round_markup(norm_tag, round_idx, total_rounds, view),
        disable_web_page_preview=True
    )





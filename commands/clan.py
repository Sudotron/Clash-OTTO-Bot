import asyncio
import os
import coc

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
    if hasattr(members[0], 'town_hall'):
        th_counts = Counter(m.town_hall for m in members if getattr(m, 'town_hall', 0) > 0)
    else:
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
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
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
    keyboard = []
    
    # Pagination for rounds
    nav = []
    if round_idx > 0:
        nav.append(InlineKeyboardButton("◀️ Prev Round", callback_data=f"cwl_r:{view}:{tag}:{round_idx - 1}"))
    if round_idx < total_rounds - 1:
        nav.append(InlineKeyboardButton("Next Round ▶️", callback_data=f"cwl_r:{view}:{tag}:{round_idx + 1}"))
    if nav:
        keyboard.append(nav)

    # Overview Pages
    keyboard.append([
        InlineKeyboardButton("🏆 Leaderboard", callback_data=f"cwl_r:leaderboard:{tag}:{round_idx}")
    ])
    keyboard.append([
        InlineKeyboardButton("❌ Missed Hits", callback_data=f"cwl_r:missed:{tag}:{round_idx}")
    ])
    keyboard.append([
        InlineKeyboardButton("👥 Members roster", callback_data=f"cwl_r:all_members:{tag}:{round_idx}")
    ])
    if view != "round" and view != "overview":
        keyboard.append([InlineKeyboardButton("◀️ Back to Round", callback_data=f"cwl_r:round:{tag}:{round_idx}")])
        
    return InlineKeyboardMarkup(keyboard)


def _cwl_overview_text(group, clan_tag: str) -> str:
    """Build CWL group overview: season, participating clans, round info."""
    season = group.season if group else 'Unknown Season'
    clans  = group.clans if group else []
    rounds = group.rounds if group else []
    total_rounds = len(rounds)
    completed = sum(1 for r in rounds if any(wt != "#0" for wt in r))

    text = (
        f"🌟 **Clan War League — {season}**\n"
        f"{'─' * 30}\n"
        f"📅 Rounds: {completed}/{total_rounds} completed\n"
        f"👥 Participating Clans ({len(clans)}):\n"
    )
    for i, c in enumerate(clans):
        ctag  = c.tag
        cname = c.name
        clvl  = c.level
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

    coc_client = context.bot_data.get("coc_client")
    if not coc_client:
        await update.message.reply_text("❌ Bot is not connected to Clash of Clans API.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = await update.message.reply_text("🌟 Fetching CWL group data...")

    # If player tag given, resolve to clan tag
    try:
        player = await coc_client.get_player(tag)
        if player.clan:
            tag = player.clan.tag
    except coc.NotFound:
        pass

    norm_tag = tag.strip().upper()
    try:
        group = await coc_client.get_league_group(norm_tag)
    except coc.NotFound:
        await msg.edit_text(
            "❌ CWL data not available.\n\n"
            "_CWL only runs for the first ~10 days of each month. "
            "Outside that window, or if the clan is not participating, no data is returned._",
            parse_mode='Markdown'
        )
        return
    except coc.Maintenance:
        await msg.edit_text("❌ Clash of Clans API is currently under maintenance.", parse_mode='Markdown')
        return
    except coc.PrivateWarLog:
        await msg.edit_text("❌ This clan's war log is private.", parse_mode='Markdown')
        return
    except Exception as e:
        await msg.edit_text(f"❌ Error fetching CWL data: {e}", parse_mode='Markdown')
        return

    context.bot_data[f"cwl_{norm_tag}"] = group

    rounds = group.rounds if group else []

    # Find latest active round
    latest = 0
    for i, r in enumerate(rounds):
        if any(wt != "#0" for wt in r):
            latest = i

    # Simulate a callback to jump straight to the latest round
    class DummyQuery:
        data = f"cwl_r:round:{norm_tag}:{latest}"
        async def answer(self): pass
        async def edit_message_text(self, text, parse_mode=None, reply_markup=None, disable_web_page_preview=None):
            await msg.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)

    class DummyUpdate:
        callback_query = DummyQuery()

    await cwl_callback(DummyUpdate(), context)


async def cwl_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts     = query.data.split(":", 3)   # cwl_r:view:tag:round_idx
    view      = parts[1] if len(parts) > 1 else "overview"
    tag       = parts[2] if len(parts) > 2 else ""
    norm_tag  = tag.strip().upper()
    round_idx = int(parts[3]) if len(parts) > 3 else 0

    coc_client = context.bot_data.get("coc_client")
    if not coc_client:
        await query.edit_message_text("❌ Bot disconnected.")
        return

    group = context.bot_data.get(f"cwl_{norm_tag}")
    if not group:
        try:
            group = await coc_client.get_league_group(norm_tag)
            context.bot_data[f"cwl_{norm_tag}"] = group
        except Exception:
            await query.edit_message_text("❌ CWL data expired. Run `/cwl` again.", parse_mode='Markdown')
            return

    rounds       = group.rounds if group else []
    total_rounds = len(rounds)

    if view == "overview":
        text = _cwl_overview_text(group, norm_tag)
        kb = _cwl_round_markup(norm_tag, round_idx, total_rounds, view)
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=kb, disable_web_page_preview=True)
        return

    if round_idx >= total_rounds:
        await query.edit_message_text("❌ Round not found.")
        return

    round_data = rounds[round_idx]
    war_tags   = [wt for wt in round_data if wt != "#0"]

    if not war_tags:
        await query.edit_message_text(
            f"⏳ Round {round_idx + 1} hasn't started yet.",
            reply_markup=_cwl_round_markup(norm_tag, round_idx, total_rounds, view)
        )
        return

    # Find the war that involves our clan
    our_war = None
    for wt in war_tags:
        try:
            wdata = await coc_client.get_league_war(wt)
            if norm_tag in (wdata.clan.tag, wdata.opponent.tag):
                our_war = wdata
                break
        except Exception:
            pass

    if not our_war:
        try:
            our_war = await coc_client.get_league_war(war_tags[0])
        except Exception:
            pass

    if not our_war:
        await query.edit_message_text(
            f"❌ Could not load Round {round_idx + 1} war data.",
            reply_markup=_cwl_round_markup(norm_tag, round_idx, total_rounds, view)
        )
        return

    if our_war.clan.tag == norm_tag:
        my_clan = our_war.clan
        opp_clan = our_war.opponent
    else:
        my_clan = our_war.opponent
        opp_clan = our_war.clan

    c_name  = my_clan.name
    c_stars = my_clan.stars
    c_dest  = my_clan.destruction
    c_members = my_clan.members or []
    c_attacks = sum(len(m.attacks) for m in c_members)
    
    o_name  = opp_clan.name
    o_tag   = opp_clan.tag
    o_stars = opp_clan.stars
    o_dest  = opp_clan.destruction
    o_members = opp_clan.members or []
    o_attacks = sum(len(m.attacks) for m in o_members)

    w_state = our_war.state
    w_size  = our_war.team_size
    league_name = group.season if group else "Unknown Season"

    if w_state == 'preparation':
        time_str    = _fmt_remaining(getattr(our_war.start_time, "time", None), "preparation")
        state_label = "In Prep"
    elif w_state == 'inWar':
        time_str    = _fmt_remaining(getattr(our_war.end_time, "time", None), "inWar")
        state_label = "In War"
    elif w_state == 'warEnded':
        end_t = getattr(our_war.end_time, "time", None)
        if end_t:
            ist_dt = end_t + timedelta(hours=5, minutes=30)
            time_str = f"\n⏰ Ended at: *{ist_dt.strftime('%H:%M')} IST*"
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

    c_roster = _th_roster(c_members)
    o_roster = _th_roster(o_members)

    if view == "attacks":
        lines = [f"🗡️ **CWL Round {round_idx + 1} — All Attacks**\n{'─'*28}\n"]
        all_attacks_raw = []
        all_members = list(c_members) + list(o_members)
        member_map  = {m.tag: m for m in all_members}
        
        for m in c_members:
            mname = m.name
            mth   = m.town_hall
            for atk in m.attacks:
                defender = member_map.get(atk.defender_tag)
                dname = defender.name if defender else 'Unknown'
                dth   = defender.town_hall if defender else '?'
                st    = atk.stars
                dest  = atk.destruction
                order = atk.order
                stars_str = '⭐' * st if st > 0 else '☆'
                all_attacks_raw.append((order, f"`{order}.` {mname}(Th{mth}) ─────> {dname}(Th{dth}) {stars_str} ({dest}%)"))

        for o in o_members:
            oname = o.name
            oth   = o.town_hall
            for atk in o.attacks:
                defender = member_map.get(atk.defender_tag)
                dname = defender.name if defender else 'Unknown'
                dth   = defender.town_hall if defender else '?'
                st    = atk.stars
                dest  = atk.destruction
                order = atk.order
                stars_str = '⭐' * st if st > 0 else '☆'
                all_attacks_raw.append((order, f"`{order}.` {dname}(Th{dth}) <───── {oname}(Th{oth}) {stars_str} ({dest}%)"))

        all_attacks_raw.sort(key=lambda x: x[0])
        all_attacks = [x[1] for x in all_attacks_raw]

        if not all_attacks:
            lines.append("❌ No attacks recorded for this round yet.")
        else:
            lines.extend(all_attacks)
        text = "\n".join(lines)
    elif view == "missed":
        lines = [f"❌ **CWL Round {round_idx + 1} — Missed Hits**\n{'─'*28}\n"]
        attacks_per_member = our_war.attacks_per_member
        missed = []
        for m in c_members:
            atk_count = len(m.attacks)
            if atk_count < attacks_per_member:
                count = attacks_per_member - atk_count
                ptag = m.tag.strip('#')
                plink = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={ptag}"
                missed.append(f"• {m.name} (TH{m.town_hall}) [#{ptag}]({plink}) — {count} missed")
        if not missed:
            lines.append("✅ **All attacks have been used!**")
        else:
            lines.extend(missed)
        text = "\n".join(lines)
    elif view == "all_members":
        lines = [f"👥 **CWL Round {round_idx + 1} — Members roster**\n{'─'*28}\n"]
        c_sorted = sorted(c_members, key=lambda x: x.map_position)
        o_sorted = sorted(o_members, key=lambda x: x.map_position)
        
        for pos in range(w_size):
            c_m = c_sorted[pos] if pos < len(c_sorted) else None
            o_m = o_sorted[pos] if pos < len(o_sorted) else None
            
            if c_m:
                c_name = c_m.name
                c_tag = c_m.tag.strip('#')
                c_link = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={c_tag}"
                c_display = f"[{c_name}]({c_link})"
            else:
                c_display = "❓ Unknown"
                
            if o_m:
                o_name = o_m.name
                o_tag = o_m.tag.strip('#')
                o_link = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={o_tag}"
                o_display = f"[{o_name}]({o_link})"
            else:
                o_display = "❓ Unknown"
                
            lines.append(f"`{pos + 1}.` {c_display} <-> {o_display}")
            
        text = "\n".join(lines)
    elif view == "leaderboard" or view == "rankings":
        await query.edit_message_text("⏳ Aggregating full season leaderboard... This may take a moment.", parse_mode='Markdown')
        war_map = context.bot_data.get(f"cwl_wars_{norm_tag}")
        if not war_map:
            war_tags = [wt for r in group.rounds for wt in r if wt != "#0"]
            tasks = [coc_client.get_league_war(wt) for wt in war_tags]
            wars = []
            import asyncio
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if not isinstance(r, Exception):
                    wars.append(r)
            context.bot_data[f"cwl_wars_{norm_tag}"] = wars
            war_map = wars
            
        clan_stats = {c.tag: {'name': c.name, 'stars': 0, 'dest': 0.0} for c in group.clans}
        for w in war_map:
            if w.state != 'preparation':
                if w.clan.tag in clan_stats:
                    clan_stats[w.clan.tag]['stars'] += w.clan.stars
                    clan_stats[w.clan.tag]['dest'] += w.clan.destruction
                if w.opponent.tag in clan_stats:
                    clan_stats[w.opponent.tag]['stars'] += w.opponent.stars
                    clan_stats[w.opponent.tag]['dest'] += w.opponent.destruction
                    
        sorted_clans = sorted(clan_stats.values(), key=lambda x: (x['stars'], x['dest']), reverse=True)
        
        lines = [f"🏆 **Season Leaderboard ({league_name})**\n{'─' * 28}\n"]
        for i, c in enumerate(sorted_clans):
            icon = "🌟" if i == 0 else "⭐"
            lines.append(f"`{i+1}.` **{c['name']}**")
            lines.append(f"   {icon} Stars: `{c['stars']}` | 💥 Dest: `{c['dest']:.1f}%`\n")
            
        text = "\n".join(lines)
    else: # Default round overview
        text = (
            f"**{c_name}**\n\n"
            f"**War Against**\n"
            f"[{o_name} ({o_tag})](https://link.clashofclans.com/en?action=OpenClanProfile&tag=%23{o_tag.replace('#', '')})\n\n"
            f"**War State**\n"
            f"CWL {league_name} - Round {round_idx + 1}/{total_rounds}\n"
            f"{state_label} ({w_size} vs {w_size}){time_str}{result_line}\n\n"
            f"**War Stats**\n"
            f"⚔️ `{c_attacks}/{w_size}`  —  `{o_attacks}/{w_size}`\n"
            f"⭐ `{c_stars}`  —  `{o_stars}`\n"
            f"💥 `{c_dest:.1f}%`  —  `{o_dest:.1f}%`\n\n"
            f"**War Composition**\n"
            f"🛡️ **{c_name}**\n"
            f"{c_roster}\n"
            f"🏴 **{o_name}**\n"
            f"{o_roster}\n"
        )

    if len(text) > 4096:
        text = text[:4090] + "\n…"

    await query.edit_message_text(
        text, parse_mode='Markdown',
        reply_markup=_cwl_round_markup(norm_tag, round_idx, total_rounds, view),
        disable_web_page_preview=True
    )

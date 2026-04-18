import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from coc_api import get_clan, get_player, get_clan_war, get_previous_wars
from commands.utils import E, _resolve_tag, _build_clan_page1, _build_members_page

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
        await update.message.reply_text(page1_text, parse_mode='Markdown', reply_markup=reply_markup)


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
                    await update.message.reply_text(text, parse_mode='Markdown')
                return
        
        if "error" in war_data:
            await msg.edit_text(f"❌ Could not find war details.\nReason: _{war_data.get('error')}_\n*(If you just made your log public, Clash API may take a few minutes to update its cache!)*", parse_mode='Markdown')
            return

    norm_tag = war_data.get('clan', {}).get('tag', tag).strip().upper()
    
    state = war_data.get('state')
    if state == 'notInWar':
        # Fetch previous wars!
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
            os = w.get('opponent', {}).get('stars', 0)
            res = "Victory" if ws > os else "Defeat" if os > ws else "Draw"
            
            text += f"**War {i+1}: {wn} vs {on}**\n"
            text += f"🏆 Result: {res} | ⭐ {ws} - {os}\n\n"
            keyboard.append([InlineKeyboardButton(f"📊 War {i+1} Analytics", callback_data=f"cwar_a:home:{norm_tag}:{i}:0")])
            
        await msg.edit_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    clan_name = war_data.get('clan', {}).get('name', 'Unknown')
    clan_stars = war_data.get('clan', {}).get('stars', 0)
    clan_dest = war_data.get('clan', {}).get('destructionPercentage', 0)
    opp_name = war_data.get('opponent', {}).get('name', 'Unknown')
    opp_stars = war_data.get('opponent', {}).get('stars', 0)
    opp_dest = war_data.get('opponent', {}).get('destructionPercentage', 0)
    team_size = war_data.get('teamSize', '?')

    text = (
        f"⚔️ **Clan War — {state.capitalize() if state else 'Unknown'}**\n"
        f"👥 Size: {team_size}v{team_size}\n\n"
        f"🛡️ **{clan_name}**\n"
        f"  ⭐ Stars: {clan_stars}   💥 Dest: {clan_dest:.1f}%\n\n"
        f"🏴 **{opp_name}**\n"
        f"  ⭐ Stars: {opp_stars}   💥 Dest: {opp_dest:.1f}%\n"
    )
    
    keyboard = [[InlineKeyboardButton("📊 War Analytics", callback_data=f"cwar_a:home:{norm_tag}:live:0")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await msg.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)


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

        text = (
            f"⚔️ **Clan War — {state.capitalize() if state else 'Unknown'}**\n"
            f"👥 Size: {team_size}v{team_size}\n\n"
            f"🛡️ **{clan_name}**\n"
            f"  ⭐ Stars: {clan_stars}   💥 Dest: {clan_dest:.1f}%\n\n"
            f"🏴 **{opp_name}**\n"
            f"  ⭐ Stars: {opp_stars}   💥 Dest: {opp_dest:.1f}%\n"
        )
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=_cwar_analytics_markup(view, norm_tag, war_index, 0, 1))
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

    chunks = []
    cur = ""
    for l in lines:
        if len(cur) + len(l) > 3800:
            chunks.append(cur)
            cur = l + "\n"
        else:
            cur += l + "\n"
    if cur: chunks.append(cur)
    
    total_pages = len(chunks) if chunks else 1
    safe_page = min(page, total_pages - 1)
    
    text = chunks[safe_page] if chunks else "No data."
    if total_pages > 1:
        text += f"\n_Page {safe_page + 1} of {total_pages}_"
        
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=_cwar_analytics_markup(view, norm_tag, war_index, safe_page, total_pages))


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


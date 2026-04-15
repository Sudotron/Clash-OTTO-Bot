import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
)

from database import init_db, link_account, get_linked_account
from coc_api import (
    get_player, get_player_stats, get_player_warhits,
    get_clan, get_clan_war
)

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ── Emoji constants ──────────────────────────────────────────────────────────
E = {
    "trophy":       "🏆",
    "versus":       "🏅",
    "shield":       "🛡️",
    "sword":        "⚔️",
    "star":         "⭐",
    "ratio":        "📊",
    "up":           "🔼",
    "down":         "🔽",
    "gold":         "💰",
    "raid":         "🗡️",
    "games":        "🎮",
    "troop":        "🪖",
    "hero":         "👑",
    "spell":        "🧪",
    "siege":        "🏰",
    "super":        "✨",
    "warning":      "⚠️",
    "player":       "👤",
    "clan":         "🛡️",
    "th":           "🏯",
    "level":        "🎖️",
    "war":          "⚔️",
    "donup":        "⬆️",
    "dondown":      "⬇️",
    "page":         "📄",
    "back":         "◀️",
    "next":         "▶️",
    "fire":         "🔥",
    "cwl":          "🌟",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def fmt_number(n) -> str:
    """Format number with commas."""
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def current_season() -> str:
    """Return current season key like '2025-04'."""
    now = datetime.utcnow()
    return now.strftime("%Y-%m")


async def _resolve_tag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get tag from args or linked account."""
    if context.args:
        return "".join(context.args)
    return await get_linked_account(update.effective_user.id)


def _build_player_page1(data: dict, stats: dict, warhits: dict, tag: str) -> str:
    """Build page 1: Season stats + All-time stats."""
    name = data.get('name', 'Unknown')
    th = data.get('townHallLevel', '?')
    exp = data.get('expLevel', '?')
    trophies = data.get('trophies', 0)
    best_trophies = data.get('bestTrophies', 0)
    builder_trophies = data.get('builderBaseTrophies', 0)
    best_builder = data.get('bestBuilderBaseTrophies', 0)
    war_stars = data.get('warStars', 0)
    clan_info = data.get('clan', {})
    clan_name = clan_info.get('name', 'None') if clan_info else 'None'
    role = data.get('role', 'none').capitalize() if data.get('role') else 'None'
    league = data.get('league', {}).get('name', 'Unranked') if data.get('league') else 'Unranked'

    # ── Season values from /v1/players ──
    atk_wins = data.get('attackWins', 0)
    def_wins = data.get('defenseWins', 0)
    donated = data.get('donations', 0)
    received = data.get('donationsReceived', 0)
    don_ratio = round(donated / received, 1) if received > 0 else float(donated)

    # ── Season values from /player/{tag}/stats ──
    season = current_season()
    stats_donations = stats.get('donations', {})
    stats_attacks = stats.get('attack_wins', {})
    stats_capital = stats.get('capital', {})
    stats_clan_games = stats.get('clan_games', {})
    stats_season_pass = stats.get('season_pass', {})

    # CG Donated / Raided from stats (current season)
    cg_donated = stats_capital.get(season, {}).get('donated', 0) if stats_capital else 0
    cg_raided = stats_capital.get(season, {}).get('raided', 0) if stats_capital else 0

    # Clan Games this season
    cg_points = stats_clan_games.get(season, 0) if stats_clan_games else 0
    if isinstance(cg_points, dict):
        cg_points = cg_points.get('points', 0)

    # ── War stats from /player/{tag}/warhits ──
    war_items = warhits.get('items', []) if isinstance(warhits, dict) else []
    total_atks = len(war_items)
    total_war_stars = sum(h.get('stars', 0) for h in war_items)
    avg_stars = round(total_war_stars / total_atks, 1) if total_atks > 0 else 0.0
    hits = sum(1 for h in war_items if h.get('stars', 0) >= 2)
    hitrate = round(hits / total_atks * 100, 1) if total_atks > 0 else 0.0

    # ── Super Troops ──
    active_supers = [
        t['name'] for t in data.get('troops', [])
        if t.get('superTroopIsActive') and t.get('village') == 'home'
    ]
    super_text = ""
    if active_supers:
        super_text = "\n✨ **Super Troops:**\n" + "".join(f"  • {s}\n" for s in active_supers)

    # ── All-time stats from achievements ──
    ach = {a['name']: a['value'] for a in data.get('achievements', [])}
    total_donated = ach.get('Friend in Need', 0)
    total_cg_points = ach.get('Games Champion', 0)
    total_cg_raided_raw = ach.get('Aggressive Capitalism', 0)
    total_cg_donated_raw = ach.get('Most Valuable Clanmate', 0)
    cwl_stars = ach.get('War League Legend', 0)

    text = (
        f"{E['player']} **{name}** | {E['th']} TH{th} | {E['level']} Lvl {exp}\n"
        f"{E['clan']} {clan_name}  •  {role}  •  {league}\n"
        f"`{tag}`\n"
        f"{'─' * 30}\n"
        f"\n📅 **Season Stats:**\n"
        f"{E['trophy']} Trophies: {fmt_number(trophies)}\n"
        f"{E['sword']} Attack Wins: {atk_wins}\n"
        f"{E['shield']} Defense Wins: {def_wins}\n"
        f"\n{E['war']} **War:**\n"
        f"{E['ratio']} Hitrate: {hitrate}%\n"
        f"{E['star']} Avg Stars: {avg_stars}\n"
        f"{E['star']} Total Stars: {total_war_stars}, {total_atks} atks\n"
        f"\n{E['troop']} **Donations:**\n"
        f"{E['donup']} Donated: {fmt_number(donated)}\n"
        f"{E['dondown']} Received: {fmt_number(received)}\n"
        f"{E['ratio']} Donation Ratio: {don_ratio}\n"
        f"\n🎉 **Event Stats:**\n"
        f"{E['gold']} CG Donated: {fmt_number(cg_donated)}\n"
        f"{E['raid']} CG Raided: {fmt_number(cg_raided)}\n"
        f"{E['games']} Clan Games: {fmt_number(cg_points)}\n"
    )
    text += super_text
    text += (
        f"\n{'─' * 30}\n"
        f"🏛️ **All Time Stats:**\n"
        f"Best: {E['trophy']}{fmt_number(best_trophies)} | {E['versus']}{fmt_number(best_builder)}\n"
        f"War: {E['star']}{fmt_number(war_stars)}\n"
        f"CWL: {E['cwl']}{fmt_number(cwl_stars)}\n"
        f"{E['troop']} Donos: {fmt_number(total_donated)}\n"
        f"{E['games']} Clan Games: {fmt_number(total_cg_points)}\n"
        f"{E['raid']} CG Raided: {fmt_number(total_cg_raided_raw)}\n"
        f"{E['gold']} CG Donated: {fmt_number(total_cg_donated_raw)}\n"
    )
    return text


def _build_player_page2(data: dict) -> str:
    """Build page 2: Troops, Siege Machines, Spells, Heroes & Equipment."""
    name = data.get('name', 'Unknown')
    th = data.get('townHallLevel', '?')

    troops_all = data.get('troops', [])
    heroes_all = data.get('heroes', [])
    equipment = data.get('heroEquipment', [])
    spells_all = data.get('spells', [])

    # Home village troops (exclude super-troop duplicates by filtering `superTroopIsActive` not in original list)
    home_troops = [t for t in troops_all if t.get('village') == 'home' and 'Super' not in t.get('name','') and not t.get('name','').startswith('Super')]
    siege_machines = [t for t in troops_all if t.get('village') == 'home' and t.get('name') in [
        'Wall Wrecker','Battle Blimp','Stone Slammer','Siege Barracks','Log Launcher','Flame Flinger','Battle Drill'
    ]]
    # Remove sieges from home troops display
    siege_names = {s['name'] for s in siege_machines}
    home_troops = [t for t in home_troops if t['name'] not in siege_names]

    home_spells = [s for s in spells_all if s.get('village') == 'home']
    home_heroes = [h for h in heroes_all if h.get('village') == 'home']

    def troop_lines(items: list) -> str:
        if not items:
            return "  None\n"
        lines = ""
        for i, t in enumerate(items):
            lvl = t.get('level', '?')
            ml = t.get('maxLevel', '?')
            maxed = "✅" if lvl == ml else ""
            lines += f"  • {t.get('name')}: {lvl}/{ml} {maxed}\n"
            if len(lines) > 2000:
                lines += "  ...(trimmed)\n"
                break
        return lines

    text = (
        f"{E['th']} **{name} | TH{th} — Troop Details**\n"
        f"{'─' * 30}\n"
        f"\n{E['troop']} **Home Troops:**\n"
    )
    text += troop_lines(home_troops)

    if siege_machines:
        text += f"\n{E['siege']} **Siege Machines:**\n"
        text += troop_lines(siege_machines)

    text += f"\n{E['spell']} **Spells:**\n"
    text += troop_lines(home_spells)

    text += f"\n{E['hero']} **Heroes:**\n"
    if home_heroes:
        for h in home_heroes:
            lvl = h.get('level', '?')
            ml = h.get('maxLevel', '?')
            maxed = "✅" if lvl == ml else ""
            text += f"  • {h.get('name')}: {lvl}/{ml} {maxed}\n"
    else:
        text += "  None\n"

    if equipment:
        text += f"\n🔮 **Hero Equipment:**\n"
        for e in equipment:
            lvl = e.get('level', '?')
            ml = e.get('maxLevel', '?')
            maxed = "✅" if lvl == ml else ""
            text += f"  • {e.get('name')}: {lvl}/{ml} {maxed}\n"

    # Builder base heroes
    bb_heroes = [h for h in heroes_all if h.get('village') == 'builderBase']
    if bb_heroes:
        text += f"\n🔨 **Builder Base Heroes:**\n"
        for h in bb_heroes:
            lvl = h.get('level', '?')
            ml = h.get('maxLevel', '?')
            text += f"  • {h.get('name')}: {lvl}/{ml}\n"

    return text


# ── Command Handlers ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Welcome to **Clash OTTO Bot** ⚔️\n\n"
        "**Commands:**\n"
        "/link `<#TAG>` — Link your CoC Account\n"
        "/player `[tag]` — Full player stats (2 pages)\n"
        "/troops `[tag]` — Troops levels\n"
        "/heroes `[tag]` — Heroes and equipment\n"
        "/spells `[tag]` — Spells levels\n"
        "/clan `[tag]` — Clan details\n"
        "/clanmembers `[tag]` — Clan member roster\n"
        "/clanwar `[tag]` — Current clan war info\n"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a tag! Example: /link #YY8PQY28")
        return
    tag = context.args[0]
    await link_account(update.effective_user.id, tag)
    await update.message.reply_text(f"✅ Successfully linked with CoC Tag: `{tag}`", parse_mode='Markdown')


async def player_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first via /link <tag>.")
        return

    msg = await update.message.reply_text("⏳ Fetching player data...")

    # Fetch all data in parallel isn't easy without asyncio.gather in python-telegram-bot handlers,
    # but we'll fetch sequentially (still fast enough)
    data = await get_player(tag)
    if "error" in data:
        await msg.edit_text(f"❌ {data['error']}")
        return

    stats = await get_player_stats(tag)
    warhits = await get_player_warhits(tag)

    # Store in bot_data keyed by tag for callback reuse
    norm_tag = tag.strip().upper()
    context.bot_data[f"pdata_{norm_tag}"] = (data, stats, warhits)

    page1_text = _build_player_page1(data, stats, warhits, norm_tag)

    keyboard = [[
        InlineKeyboardButton(f"{E['next']} Troops & Heroes", callback_data=f"player_p2:{norm_tag}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await msg.edit_text(page1_text, parse_mode='Markdown', reply_markup=reply_markup)


async def player_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 1)
    action = parts[0]
    tag = parts[1] if len(parts) > 1 else ""

    # Retrieve cached data or re-fetch
    norm_tag = tag.strip().upper()
    cached = context.bot_data.get(f"pdata_{norm_tag}")

    if action == "player_p2":
        if cached:
            data, stats, warhits = cached
        else:
            data = await get_player(tag)
            stats = await get_player_stats(tag)
            warhits = await get_player_warhits(tag)
            if "error" in data:
                await query.edit_message_text(f"❌ {data['error']}")
                return
            context.bot_data[f"pdata_{norm_tag}"] = (data, stats, warhits)

        page2_text = _build_player_page2(data)
        keyboard = [[
            InlineKeyboardButton(f"{E['back']} Season Stats", callback_data=f"player_p1:{norm_tag}")
        ]]
        await query.edit_message_text(
            page2_text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "player_p1":
        if cached:
            data, stats, warhits = cached
        else:
            data = await get_player(tag)
            stats = await get_player_stats(tag)
            warhits = await get_player_warhits(tag)
            if "error" in data:
                await query.edit_message_text(f"❌ {data['error']}")
                return
            context.bot_data[f"pdata_{norm_tag}"] = (data, stats, warhits)

        page1_text = _build_player_page1(data, stats, warhits, norm_tag)
        keyboard = [[
            InlineKeyboardButton(f"{E['next']} Troops & Heroes", callback_data=f"player_p2:{norm_tag}")
        ]]
        await query.edit_message_text(
            page1_text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def troops_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    data = await get_player(tag)
    if "error" in data:
        await update.message.reply_text(f"❌ {data['error']}")
        return

    troops = [t for t in data.get('troops', []) if t.get('village') == 'home' and 'Super' not in t.get('name','')]
    text = f"{E['troop']} **{data.get('name')} — Home Troops:**\n"
    for t in troops:
        lvl, ml = t.get('level'), t.get('maxLevel')
        maxed = " ✅" if lvl == ml else ""
        text += f"• {t.get('name')}: Lvl {lvl}/{ml}{maxed}\n"
    if len(text) > 4000:
        text = text[:4000] + "...\n(Trimmed)"
    await update.message.reply_text(text, parse_mode='Markdown')


async def heroes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    data = await get_player(tag)
    if "error" in data:
        await update.message.reply_text(f"❌ {data['error']}")
        return

    heroes = data.get('heroes', [])
    equipment = data.get('heroEquipment', [])

    text = f"{E['hero']} **{data.get('name')} — Heroes:**\n"
    for h in heroes:
        if h.get('village') == 'home':
            lvl, ml = h.get('level'), h.get('maxLevel')
            maxed = " ✅" if lvl == ml else ""
            text += f"• {h.get('name')}: Lvl {lvl}/{ml}{maxed}\n"

    if equipment:
        text += "\n🔮 **Hero Equipment:**\n"
        for e in equipment:
            lvl, ml = e.get('level'), e.get('maxLevel')
            maxed = " ✅" if lvl == ml else ""
            text += f"• {e.get('name')}: Lvl {lvl}/{ml}{maxed}\n"

    if text == f"{E['hero']} **{data.get('name')} — Heroes:**\n":
        text = "No heroes found."

    await update.message.reply_text(text, parse_mode='Markdown')


async def spells_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    data = await get_player(tag)
    if "error" in data:
        await update.message.reply_text(f"❌ {data['error']}")
        return

    spells = [s for s in data.get('spells', []) if s.get('village') == 'home']
    if not spells:
        await update.message.reply_text("No spells found.")
        return

    text = f"{E['spell']} **{data.get('name')} — Spells:**\n"
    for s in spells:
        lvl, ml = s.get('level'), s.get('maxLevel')
        maxed = " ✅" if lvl == ml else ""
        text += f"• {s.get('name')}: Lvl {lvl}/{ml}{maxed}\n"
    await update.message.reply_text(text, parse_mode='Markdown')


def _role_icon(role: str) -> str:
    return {"leader": "👑", "coLeader": "🥇", "admin": "🥈", "member": "🥉"}.get(role, "👤")


def _build_clan_page1(data: dict) -> str:
    """Build clan page 1: all clan details."""
    name = data.get('name', 'Unknown')
    tag  = data.get('tag', '?')
    lvl  = data.get('clanLevel', '?')
    members = data.get('members', 0)
    pts  = data.get('clanPoints', 0)
    bb_pts = data.get('clanBuilderBasePoints', 0)
    req_trophies = data.get('requiredTrophies', 0)
    req_th = data.get('requiredTownhallLevel', 1)
    location = data.get('location', {}).get('name', 'International') if data.get('location') else 'International'
    desc = (data.get('description') or 'No description.').strip()

    # War stats
    war_wins   = data.get('warWins', 0)
    war_streak = data.get('warWinStreak', 0)
    is_public  = data.get('isWarLogPublic', False)
    war_losses = data.get('warLosses', '?') if is_public else 'Hidden Log'
    war_freq   = data.get('warFrequency', '?').capitalize()

    # Leagues
    cwl_league = data.get('warLeague', {}).get('name', 'Unranked') if data.get('warLeague') else 'Unranked'
    cap_league = data.get('capitalLeague', {}).get('name', '') if data.get('capitalLeague') else ''
    cap_hall   = data.get('clanCapital', {}).get('capitalHallLevel', '?') if data.get('clanCapital') else '?'

    # Find leader from memberList
    leader_name = 'Unknown'
    for m in data.get('memberList', []):
        if m.get('role') == 'leader':
            leader_name = m.get('name', 'Unknown')
            break

    # Win ratio (only if war log public)
    if is_public:
        total_wars = war_wins + (data.get('warLosses', 0) + data.get('warTies', 0))
        ratio = f"{round(war_wins / total_wars * 100, 1)}%" if total_wars > 0 else "0%"
    else:
        ratio = "Hidden Log"

    text = (
        f"🛡️ **{name}**\n"
        f"`{tag}`\n"
        f"{'─'*30}\n"
        f"🏆 {fmt_number(pts)} | 🏅 {fmt_number(bb_pts)}\n"
        f"Required: 🏆 {req_trophies}  •  🏯 TH{req_th}+\n"
        f"🌏 Location: {location}\n"
        f"\n"
        f"👑 Leader: {leader_name}\n"
        f"📈 Level: {lvl}\n"
        f"👥 Members: {members}/50\n"
        f"\n"
        f"🌟 CWL: {cwl_league}\n"
        f"🏛️ Capital Hall: Lv{cap_hall}  •  {cap_league}\n"
        f"⚔️ War Freq: {war_freq}\n"
        f"⬆️ Wars Won: {war_wins}\n"
        f"⬇️ Wars Lost: {war_losses}\n"
        f"🔥 War Streak: {war_streak}\n"
        f"📊 Win Ratio: {ratio}\n"
        f"\n"
        f"📖 *Description:*\n"
        f"_{desc}_\n"
    )
    return text


MEMBERS_PER_PAGE = 15


def _build_members_page(data: dict, page: int) -> tuple:
    """Build a paginated member page. Returns (caption_text, InlineKeyboardMarkup)."""
    name     = data.get('name', 'Unknown')
    norm_tag = data.get('tag', '').strip().upper()
    all_members = sorted(data.get('memberList', []), key=lambda m: m.get('clanRank', 99))
    total        = len(all_members)
    total_pages  = max(1, (total + MEMBERS_PER_PAGE - 1) // MEMBERS_PER_PAGE)
    page         = max(0, min(page, total_pages - 1))

    start        = page * MEMBERS_PER_PAGE
    end          = min(start + MEMBERS_PER_PAGE, total)
    page_members = all_members[start:end]

    # ── Caption text ──────────────────────────────────────────────────────
    text = (
        f"👥 *{name} — Members ({total}/50)*\n"
        f"Page {page + 1}/{total_pages}  •  #{start + 1}–{end}\n"
        f"{'─' * 28}\n"
    )
    for m in page_members:
        rank  = m.get('clanRank', '?')
        icon  = _role_icon(m.get('role', 'member'))
        mname = m.get('name', 'Unknown')[:14]
        th    = m.get('townHallLevel', '?')
        troph = m.get('trophies', 0)
        mtag  = m.get('tag', '?')
        text += f"`{rank}.`{icon} *{mname}*  TH{th} 🏆{troph}\n`    {mtag}`\n"

    # ── Keyboard ──────────────────────────────────────────────────────────
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"clan_members:{norm_tag}:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="clan_noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶️ Next", callback_data=f"clan_members:{norm_tag}:{page + 1}"))

    keyboard = [nav_row, [InlineKeyboardButton("◀️ Clan Details", callback_data=f"clan_p1:{norm_tag}")]]
    return text, InlineKeyboardMarkup(keyboard)



async def clan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a clan tag or link a player account first.")
        return

    # Show a quick loading indicator, then delete it once photo is ready
    loading = await update.message.reply_text("⏳ Fetching clan data...")

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

    # Delete the loading text, then send ONE combined photo+caption message
    await loading.delete()
    if badge_url:
        await update.message.reply_photo(
            photo=badge_url,
            caption=page1_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        # Fallback if no badge
        await update.message.reply_text(page1_text, parse_mode='Markdown', reply_markup=reply_markup)


async def clan_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Silently ignore the page-indicator "noop" button
    if query.data == "clan_noop":
        await query.answer()
        return

    await query.answer()

    # Parse: action:tag  OR  action:tag:page
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

    # ── Page 1: clan details ──────────────────────────────────────────────
    if action == "clan_p1":
        page1_text = _build_clan_page1(data)
        keyboard   = [[InlineKeyboardButton("👥 Members List", callback_data=f"clan_p2:{norm_tag}")]]
        await query.edit_message_caption(
            caption=page1_text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ── Page 2: launch paginated members (page 0) ─────────────────────────
    elif action == "clan_p2":
        text, markup = _build_members_page(data, 0)
        await query.edit_message_caption(
            caption=text, parse_mode='Markdown', reply_markup=markup
        )

    # ── Members pagination ────────────────────────────────────────────────
    elif action == "clan_members":
        text, markup = _build_members_page(data, page)
        await query.edit_message_caption(
            caption=text, parse_mode='Markdown', reply_markup=markup
        )


async def clanmembers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick shortcut — just sends the member roster as text."""
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    msg = await update.message.reply_text("⏳ Fetching members...")
    data = await get_clan(tag)
    if "error" in data:
        pdata = await get_player(tag)
        if "error" not in pdata and pdata.get('clan'):
            data = await get_clan(pdata['clan']['tag'])
        if "error" in data:
            await msg.edit_text("❌ Could not find clan details.")
            return

    await msg.edit_text(_build_clan_page2(data), parse_mode='Markdown')


async def clanwar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    data = await get_clan_war(tag)
    if "error" in data:
        pdata = await get_player(tag)
        if "error" not in pdata and pdata.get('clan'):
            data = await get_clan_war(pdata['clan']['tag'])
        else:
            await update.message.reply_text("❌ Could not find war details.")
            return

    state = data.get('state')
    if state == 'notInWar':
        await update.message.reply_text("⚔️ The clan is not currently in a war.")
        return

    clan_name = data.get('clan', {}).get('name', 'Unknown')
    clan_stars = data.get('clan', {}).get('stars', 0)
    clan_dest = data.get('clan', {}).get('destructionPercentage', 0)
    opp_name = data.get('opponent', {}).get('name', 'Unknown')
    opp_stars = data.get('opponent', {}).get('stars', 0)
    opp_dest = data.get('opponent', {}).get('destructionPercentage', 0)
    team_size = data.get('teamSize', '?')

    text = (
        f"⚔️ **Clan War — {state.capitalize()}**\n"
        f"👥 Size: {team_size}v{team_size}\n\n"
        f"🛡️ **{clan_name}**\n"
        f"  ⭐ Stars: {clan_stars}   💥 Dest: {clan_dest:.1f}%\n\n"
        f"🏴 **{opp_name}**\n"
        f"  ⭐ Stars: {opp_stars}   💥 Dest: {opp_dest:.1f}%\n"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    token = os.getenv("TG_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logging.error("No valid TG_BOT_TOKEN found in .env!")
        return

    import asyncio
    asyncio.run(init_db())

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link_cmd))
    app.add_handler(CommandHandler("player", player_cmd))
    app.add_handler(CommandHandler("troops", troops_cmd))
    app.add_handler(CommandHandler("heroes", heroes_cmd))
    app.add_handler(CommandHandler("spells", spells_cmd))
    app.add_handler(CommandHandler("clan", clan_cmd))
    app.add_handler(CommandHandler("clanmembers", clanmembers_cmd))
    app.add_handler(CommandHandler("clanwar", clanwar_cmd))

    # Inline page navigation
    app.add_handler(CallbackQueryHandler(player_page_callback, pattern=r"^player_p[12]:"))
    app.add_handler(CallbackQueryHandler(clan_page_callback,   pattern=r"^(clan_p[12]|clan_members|clan_noop).*"))

    logging.info("Starting bot...")
    app.run_polling()


if __name__ == '__main__':
    main()

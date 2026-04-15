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
    get_clan, get_clan_members, get_clan_war
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


async def clan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    data = await get_clan(tag)
    if "error" in data:
        pdata = await get_player(tag)
        if "error" not in pdata and pdata.get('clan'):
            data = await get_clan(pdata['clan']['tag'])
        else:
            await update.message.reply_text("❌ Could not find clan details. Is it a valid clan tag?")
            return

    name = data.get('name', 'Unknown')
    lvl = data.get('clanLevel', '?')
    members = data.get('members', 0)
    pts = data.get('clanPoints', 0)
    desc = data.get('description', 'No description.')

    text = (
        f"🛡️ **{name}** ({data.get('tag')})\n"
        f"📈 Level: {lvl}\n"
        f"👥 Members: {members}/50\n"
        f"🏆 Points: {fmt_number(pts)}\n\n"
        f"📖 _{desc}_"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


async def clanmembers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    data = await get_clan_members(tag)
    if "error" in data:
        pdata = await get_player(tag)
        if "error" not in pdata and pdata.get('clan'):
            data = await get_clan_members(pdata['clan']['tag'])
        else:
            await update.message.reply_text("❌ Could not find clan details.")
            return

    member_list = data.get('items', [])
    if not member_list:
        await update.message.reply_text("No members found or invalid clan.")
        return

    text = "👥 **Clan Members:**\n"
    for m in member_list[:50]:
        text += f"{m.get('clanRank')}. {m.get('name')} — {m.get('role','').capitalize()} (🏆 {m.get('trophies')})\n"
    if len(text) > 4000:
        text = text[:4000] + "...\n"
    await update.message.reply_text(text, parse_mode='Markdown')


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

    # Inline page navigation for /player
    app.add_handler(CallbackQueryHandler(player_page_callback, pattern=r"^player_p[12]:"))

    logging.info("Starting bot...")
    app.run_polling()


if __name__ == '__main__':
    main()

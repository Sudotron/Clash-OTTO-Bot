from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import get_linked_account

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


async def _resolve_tag(update: Update, context: ContextTypes.DEFAULT_TYPE, entity_type: str = 'player') -> str:
    """Get tag from args or intelligently check linked accounts based on type."""
    if context.args:
        return "".join(context.args)
        
    tag = await get_linked_account(update.effective_user.id, entity_type)
    
    # If we specifically wanted a clan but they only linked a player, 
    # we return their player tag so the caller can extract the clan ID natively!
    if not tag and entity_type == 'clan':
        tag = await get_linked_account(update.effective_user.id, 'player')
        
    # Same logic inverted
    if not tag and entity_type == 'player':
        tag = await get_linked_account(update.effective_user.id, 'clan')
        
    return tag


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

    clean_tag = tag.replace('#', '')
    p_link = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag=%23{clean_tag}"
    
    c_clean_tag = clan_info.get('tag', '').replace('#', '') if clan_info else ''
    c_link = f"https://link.clashofclans.com/en?action=OpenClanProfile&tag=%23{c_clean_tag}" if c_clean_tag else ""
    clan_name_str = f"[{clan_name}]({c_link})" if c_link else clan_name

    text = (
        f"{E['player']} **[{name}]({p_link})** | {E['th']} TH{th} | {E['level']} Lvl {exp}\n"
        f"{E['clan']} {clan_name_str}  •  {role}  •  {league}\n"
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

    clean_tag = tag.replace('#', '')
    c_link = f"https://link.clashofclans.com/en?action=OpenClanProfile&tag=%23{clean_tag}"

    text = (
        f"🛡️ **[{name}]({c_link})**\n"
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

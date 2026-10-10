"""Extra automatic posts, error alerts and commands for the FPL bot.

Automatic jobs (all scheduled from bot/schedulers/setup.py):
  deadline_watch      reminder N hours before the next deadline
  pre_deadline_watch  captain poll, most-transferred list, FDR table, DGW/BGW chip hints
  price_watch         price rises / falls
  injury_watch        injury and availability changes for popular players
  gw_summary_watch    summary after a gameweek is finished

Commands: /team <fpl id>, /league <league id>
Errors in any job are forwarded to the admins via guarded().
"""
from __future__ import annotations

import html
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram.ext import CommandHandler

from bot.config.settings import get_settings
from bot.services.analytics import captain_picks, current_event

log = logging.getLogger(__name__)

STATE_PATH = Path('data/extras_state.json')

PUBLIC_COMMANDS = False   # True -> /team and /league answer everybody, not only admins
POPULAR_OWNERSHIP = 5.0   # injury alerts only for players owned by at least this % of managers
POLL_HOURS = 12           # captain poll this many hours before the deadline
TRANSFERS_HOURS = 1       # most-transferred list this many hours before the deadline
FDR_HOURS = 36            # fixture difficulty table this many hours before the deadline
FDR_SPAN = 5              # how many gameweeks the FDR table covers
CHIP_LOOKAHEAD = 3        # look for double / blank gameweeks this many GWs ahead
BLANK_MIN_TEAMS = 4       # a gameweek counts as blank when at least this many teams do not play

STATUS_UZ = {
    'i': '🚑 Jarohat',
    'd': '⚠️ Shubhali',
    's': '🟥 Diskvalifikatsiya',
    'u': '❌ Mavjud emas',
    'n': '❌ Mavjud emas',
    'a': '✅ Qaytdi',
}


# ---------------------------------------------------------------- state ----
def _load() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def state_get(key, default=None):
    return _load().get(key, default)


def state_set(key, value) -> None:
    state = _load()
    state[key] = value
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_PATH)


def is_done(key: str) -> bool:
    return bool(state_get('done:' + key, False))


def mark_done(key: str) -> None:
    state_set('done:' + key, True)


# -------------------------------------------------------------- helpers ----
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace('Z', '+00:00'))


def _fmt_int(n) -> str:
    return f'{int(n):,}'.replace(',', ' ')


def _price(cost) -> str:
    return f'£{cost / 10:.1f}m'


def _teams(data: dict) -> dict:
    return {t['id']: t['short_name'] for t in data.get('teams', [])}


def _by_id(data: dict) -> dict:
    return {p['id']: p for p in data.get('elements', [])}


def _pname(player: dict) -> str:
    return html.escape(player.get('web_name', '?'))


def next_deadline_event(data: dict):
    """(event, deadline) of the nearest gameweek whose deadline is still ahead."""
    now = _now()
    upcoming = []
    for event in data.get('events', []):
        raw = event.get('deadline_time')
        if raw and not event.get('finished'):
            deadline = _parse_dt(raw)
            if deadline > now:
                upcoming.append((deadline, event))
    if not upcoming:
        return None
    deadline, event = min(upcoming, key=lambda x: x[0])
    return event, deadline


async def _post(app, text: str) -> None:
    await app.bot.send_message(chat_id=get_settings().channel_id, text=text,
                               parse_mode='HTML', disable_web_page_preview=True)


# ------------------------------------------------------ error reporting ----
_last_error: dict[str, float] = {}


async def notify_admins(app, text: str) -> None:
    for admin_id in get_settings().admins:
        try:
            await app.bot.send_message(chat_id=admin_id, text=text[:4000])
        except Exception as exc:
            log.warning('could not notify admin %s: %s', admin_id, exc)


def guarded(name: str, fn):
    """Wrap a scheduled job so failures are logged and sent to the admins
    (at most once per hour per job, to avoid spam)."""
    async def run(app):
        try:
            await fn(app)
        except Exception as exc:
            log.exception('%s failed', name)
            if time.time() - _last_error.get(name, 0) > 3600:
                _last_error[name] = time.time()
                await notify_admins(app, f'⚠️ Bot xatosi ({name}): {type(exc).__name__}: {exc}')
    return run


# ---------------------------------------------------------- 1. deadline ----
async def deadline_watch(app):
    s = get_settings()
    if not s.auto_posts_enabled:
        return
    data = await app.bot_data['fpl'].bootstrap()
    found = next_deadline_event(data)
    if not found:
        return
    event, deadline = found
    seconds_left = (deadline - _now()).total_seconds()
    key = f"deadline_gw{event['id']}"
    if seconds_left / 3600 > s.deadline_hours or is_done(key):
        return
    tz = ZoneInfo(s.timezone)
    minutes = max(int(seconds_left // 60), 0)
    when = deadline.astimezone(tz).strftime('%d.%m.%Y %H:%M')
    text = (f"<b>⏰ GW{event['id']} DEADLINE yaqinlashmoqda</b>\n\n"
            f'Deadline: <b>{when}</b> (Toshkent vaqti)\n'
            f'Qolgan vaqt: <b>{minutes // 60} soat {minutes % 60} daqiqa</b>\n\n'
            'Captain, vice-captain va transferlaringizni tekshiring.')
    await _post(app, text)
    mark_done(key)


# ------------------------------------------------- 2. price changes -------
def price_changes_text(data: dict, old: dict) -> str | None:
    teams = _teams(data)
    risers, fallers = [], []
    for p in data.get('elements', []):
        prev = old.get(str(p['id']))
        cost = p.get('now_cost')
        if prev is None or cost is None or prev == cost:
            continue
        row = (float(p.get('selected_by_percent') or 0), p, prev, cost)
        (risers if cost > prev else fallers).append(row)
    if not risers and not fallers:
        return None

    def block(title, rows):
        if not rows:
            return []
        rows.sort(key=lambda r: r[0], reverse=True)
        out = ['', title]
        for _, p, prev, cost in rows[:20]:
            out.append(f"• <b>{_pname(p)}</b> ({teams.get(p['team'], '?')}) {_price(prev)} → {_price(cost)}")
        return out

    lines = ['<b>💰 NARX O‘ZGARISHI</b>']
    lines += block('📈 <b>Qimmatlashdi</b>', risers)
    lines += block('📉 <b>Arzonlashdi</b>', fallers)
    return '\n'.join(lines)


async def price_watch(app):
    s = get_settings()
    if not s.auto_posts_enabled:
        return
    data = await app.bot_data['fpl'].bootstrap()
    elements = data.get('elements', [])
    if not elements:
        return
    new = {str(p['id']): p['now_cost'] for p in elements if p.get('now_cost') is not None}
    old = state_get('prices')
    if old:
        text = price_changes_text(data, old)
        if text:
            await _post(app, text)
    state_set('prices', new)


# ------------------------------------------------------- 3. injuries ------
def injury_changes(data: dict, old: dict) -> list[str]:
    teams = _teams(data)
    lines = []
    for p in data.get('elements', []):
        if float(p.get('selected_by_percent') or 0) < POPULAR_OWNERSHIP:
            continue
        prev = old.get(str(p['id']))
        cur = [p.get('status'), p.get('news') or '']
        if prev is None or prev == cur:
            continue
        status = p.get('status')
        if status == 'a' and prev[0] == 'a':
            continue
        chance = p.get('chance_of_playing_next_round')
        chance_txt = f' ({chance}%)' if chance is not None else ''
        news = p.get('news') or ''
        extra = f' — {html.escape(news)}' if news else ''
        label = STATUS_UZ.get(status, str(status))
        lines.append(f"{label}: <b>{_pname(p)}</b> ({teams.get(p['team'], '?')}){chance_txt}{extra}")
    return lines


async def injury_watch(app):
    s = get_settings()
    if not s.auto_posts_enabled:
        return
    data = await app.bot_data['fpl'].bootstrap()
    elements = data.get('elements', [])
    if not elements:
        return
    snapshot = {str(p['id']): [p.get('status'), p.get('news') or ''] for p in elements}
    old = state_get('injuries')
    if old:
        lines = injury_changes(data, old)
        if lines:
            await _post(app, '<b>🏥 JAROHAT VA HOLAT YANGILIKLARI</b>\n\n' + '\n'.join(lines[:15]))
    state_set('injuries', snapshot)


# --------------------------------------------------- 4. GW summary --------
def gw_summary_text(data: dict, event: dict, live: dict) -> str:
    players, teams = _by_id(data), _teams(data)
    lines = [f"<b>🏁 GW{event['id']} YAKUNLANDI</b>", '']
    if event.get('average_entry_score') is not None:
        lines.append(f"📊 O‘rtacha ball: <b>{event['average_entry_score']}</b>")
    if event.get('highest_score') is not None:
        lines.append(f"🔝 Eng yuqori ball: <b>{event['highest_score']}</b>")
    for label, field in (('👑 Eng ko‘p captain qilingan', 'most_captained'),
                         ('📥 Eng ko‘p olingan', 'most_transferred_in')):
        p = players.get(event.get(field))
        if p:
            lines.append(f"{label}: <b>{_pname(p)}</b> ({teams.get(p['team'], '?')})")
    elements = live.get('elements', []) if isinstance(live, dict) else []
    top = sorted(elements, key=lambda e: e.get('stats', {}).get('total_points', 0), reverse=True)[:5]
    rows = []
    for i, e in enumerate(top, 1):
        p = players.get(e['id'])
        if p:
            rows.append(f"{i}. <b>{_pname(p)}</b> ({teams.get(p['team'], '?')}) — "
                        f"{e['stats']['total_points']} ball")
    if rows:
        lines += ['', '⭐️ <b>GW eng yaxshi o‘yinchilari</b>'] + rows
    return '\n'.join(lines)


async def gw_summary_watch(app):
    s = get_settings()
    if not s.auto_posts_enabled:
        return
    fpl = app.bot_data['fpl']
    data = await fpl.bootstrap()
    finished = [e for e in data.get('events', []) if e.get('finished') and e.get('data_checked')]
    if not state_get('gw_seeded'):
        # first run: remember already finished gameweeks so old summaries are not posted
        for e in finished:
            mark_done(f"gw_summary_{e['id']}")
        state_set('gw_seeded', True)
        return
    pending = [e for e in finished if not is_done(f"gw_summary_{e['id']}")]
    if not pending:
        return
    event = max(pending, key=lambda e: e['id'])
    live = await fpl.live(event['id'])
    await _post(app, gw_summary_text(data, event, live))
    for e in pending:
        mark_done(f"gw_summary_{e['id']}")


# ------------------------------------------- 5. pre-deadline posts --------
def transfers_text(data: dict, gw: int) -> str | None:
    teams = _teams(data)
    elements = data.get('elements', [])
    if not elements:
        return None

    def block(title, field):
        top = sorted(elements, key=lambda p: p.get(field, 0), reverse=True)[:5]
        rows = [f"{i}. <b>{_pname(p)}</b> ({teams.get(p['team'], '?')}) — {_fmt_int(p.get(field, 0))}"
                for i, p in enumerate(top, 1) if p.get(field, 0) > 0]
        return [title] + rows if rows else []

    lines = [f'<b>🔁 GW{gw}: TRANSFERLAR</b>', '']
    lines += block('📥 <b>Eng ko‘p olinganlar</b>', 'transfers_in_event')
    out = block('📤 <b>Eng ko‘p sotilganlar</b>', 'transfers_out_event')
    if out:
        lines += [''] + out
    return '\n'.join(lines) if len(lines) > 2 else None


def fdr_text(data: dict, fixtures: list, start_gw: int, span: int = FDR_SPAN) -> str | None:
    teams = _teams(data)
    table: dict[int, list] = {}
    for f in fixtures:
        ev = f.get('event')
        if ev is None or not (start_gw <= ev < start_gw + span):
            continue
        table.setdefault(f['team_h'], []).append((teams.get(f['team_a'], '?'), 'H', f.get('team_h_difficulty', 3)))
        table.setdefault(f['team_a'], []).append((teams.get(f['team_h'], '?'), 'A', f.get('team_a_difficulty', 3)))
    if not table:
        return None
    avg = {t: sum(x[2] for x in rows) / len(rows) for t, rows in table.items()}
    ranked = sorted(avg, key=lambda t: (avg[t], -len(table[t])))

    def line(i, t):
        opponents = ', '.join(f'{o} {side}' for o, side, _ in table[t])
        return f"{i}. <b>{teams.get(t, '?')}</b> — {avg[t]:.1f}  ({opponents})"

    easy = [line(i, t) for i, t in enumerate(ranked[:5], 1)]
    hard = [line(i, t) for i, t in enumerate(reversed(ranked[-5:]), 1)]
    return '\n'.join([f'<b>📅 GW{start_gw}–{start_gw + span - 1}: FIXTURE QIYINCHILIGI</b>', '',
                      '🟢 <b>Eng oson kalendar</b>'] + easy + ['', '🔴 <b>Eng qiyin kalendar</b>'] + hard +
                     ['', '<em>1 — eng oson, 5 — eng qiyin.</em>'])


def chip_hints(data: dict, fixtures: list, gws) -> list[tuple[str, str]]:
    """(dedup key, post text) for double / blank gameweeks among `gws`."""
    teams = _teams(data)
    hints = []
    for gw in gws:
        counts: dict[int, int] = {}
        for f in fixtures:
            if f.get('event') == gw:
                counts[f['team_h']] = counts.get(f['team_h'], 0) + 1
                counts[f['team_a']] = counts.get(f['team_a'], 0) + 1
        if not counts:
            continue
        double = sorted(teams.get(t, '?') for t, c in counts.items() if c >= 2)
        blank = sorted(teams[t] for t in teams if t not in counts)
        if double:
            hints.append((f'chip_dgw_gw{gw}',
                          f'<b>⚡ GW{gw}: DOUBLE GAMEWEEK</b>\n\n'
                          f"Ikki marta o‘ynaydigan jamoalar: <b>{', '.join(double)}</b>\n\n"
                          '💡 Bench Boost yoki Triple Captain uchun qulay hafta bo‘lishi mumkin.'))
        if len(blank) >= BLANK_MIN_TEAMS:
            hints.append((f'chip_bgw_gw{gw}',
                          f'<b>⚠️ GW{gw}: BLANK GAMEWEEK</b>\n\n'
                          f"O‘ynamaydigan jamoalar: <b>{', '.join(blank)}</b>\n\n"
                          '💡 Free Hit chipi uchun qulay hafta bo‘lishi mumkin.'))
    return hints


async def pre_deadline_watch(app):
    s = get_settings()
    if not s.auto_posts_enabled:
        return
    fpl = app.bot_data['fpl']
    data = await fpl.bootstrap()
    found = next_deadline_event(data)
    if not found:
        return
    event, deadline = found
    gw = event['id']
    hours = (deadline - _now()).total_seconds() / 3600

    if hours <= POLL_HOURS and not is_done(f'poll_gw{gw}'):
        picks = captain_picks(data, 4)
        if len(picks) >= 2:
            options = [p.name[:90] for p in picks] + ['Boshqa']
            await app.bot.send_poll(chat_id=s.channel_id, question=f'GW{gw}: Kim captain bo‘ladi?',
                                    options=options, is_anonymous=True)
            mark_done(f'poll_gw{gw}')

    if hours <= TRANSFERS_HOURS and not is_done(f'transfers_gw{gw}'):
        text = transfers_text(data, gw)
        if text:
            await _post(app, text)
            mark_done(f'transfers_gw{gw}')

    fixtures = None
    if hours <= FDR_HOURS and not is_done(f'fdr_gw{gw}'):
        fixtures = await fpl.fixtures()
        text = fdr_text(data, fixtures, gw) if fixtures else None
        if text:
            await _post(app, text)
            mark_done(f'fdr_gw{gw}')

    pending = [g for g in range(gw, gw + CHIP_LOOKAHEAD)]
    if any(not (is_done(f'chip_dgw_gw{g}') and is_done(f'chip_bgw_gw{g}')) for g in pending):
        if fixtures is None:
            fixtures = await fpl.fixtures()
        for key, text in chip_hints(data, fixtures or [], pending):
            if not is_done(key):
                await _post(app, text)
                mark_done(key)


# ---------------------------------------------------------- commands -------
def _allowed(update) -> bool:
    if PUBLIC_COMMANDS:
        return True
    user = update.effective_user
    return bool(user and user.id in get_settings().admins)


async def team_cmd(update, context):
    if not _allowed(update):
        await update.effective_message.reply_text('Ruxsat yo‘q.')
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text('Foydalanish: /team 123456  (123456 — sizning FPL ID raqamingiz)')
        return
    fpl = context.bot_data['fpl']
    entry_id = int(context.args[0])
    info = await fpl.get(f'/entry/{entry_id}/')
    if not info or 'name' not in info:
        await update.message.reply_text('Bunday jamoa topilmadi.')
        return
    data = await fpl.bootstrap()
    event = current_event(data)
    gw = event['id'] if event else info.get('current_event') or 1
    picks = await fpl.get(f'/entry/{entry_id}/event/{gw}/picks/')
    if not picks or not picks.get('picks'):
        await update.message.reply_text(f"<b>{html.escape(info['name'])}</b>\nGW{gw} tarkibi hali mavjud emas.",
                                        parse_mode='HTML')
        return
    live = await fpl.live(gw)
    points = {e['id']: e.get('stats', {}).get('total_points', 0) for e in live.get('elements', [])}
    players = _by_id(data)
    positions = {t['id']: t['singular_name_short'] for t in data.get('element_types', [])}
    history = picks.get('entry_history', {})

    xi, bench = [], []
    for pk in sorted(picks['picks'], key=lambda x: x['position']):
        p = players.get(pk['element'])
        if not p:
            continue
        mark = ' (C)' if pk.get('is_captain') else ' (V)' if pk.get('is_vice_captain') else ''
        raw = points.get(pk['element'], 0)
        multiplier = pk.get('multiplier', 1)
        pos = positions.get(p['element_type'], '?')
        if multiplier > 0:
            xi.append(f'{pos} <b>{_pname(p)}</b>{mark} — {raw * multiplier}')
        else:
            bench.append(f'{pos} {_pname(p)} — {raw}')

    manager = html.escape(f"{info.get('player_first_name', '')} {info.get('player_last_name', '')}".strip())
    lines = [f"<b>{html.escape(info['name'])}</b> — {manager}", '',
             f"GW{gw}: <b>{history.get('points', '?')}</b> ball | Umumiy: <b>{history.get('total_points', '?')}</b>"]
    if history.get('rank'):
        lines.append(f"GW reytingi: {_fmt_int(history['rank'])}")
    if info.get('summary_overall_rank'):
        lines.append(f"Umumiy reyting: {_fmt_int(info['summary_overall_rank'])}")
    if picks.get('active_chip'):
        lines.append(f"Chip: {html.escape(str(picks['active_chip']))}")
    lines += ['', '<b>Asosiy tarkib</b>'] + xi
    if bench:
        lines += ['', '<b>Zaxira</b>'] + bench
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')


async def league_cmd(update, context):
    if not _allowed(update):
        await update.effective_message.reply_text('Ruxsat yo‘q.')
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text('Foydalanish: /league 123456  (123456 — liga ID raqami)')
        return
    result = await context.bot_data['fpl'].get(f'/leagues-classic/{int(context.args[0])}/standings/')
    rows = (result.get('standings') or {}).get('results', []) if isinstance(result, dict) else []
    if not rows:
        await update.message.reply_text('Liga topilmadi yoki jadval bo‘sh.')
        return
    title = html.escape((result.get('league') or {}).get('name', 'Liga'))
    lines = [f'<b>🏆 {title}</b>', '']
    for r in rows[:15]:
        lines.append(f"{r.get('rank', '?')}. <b>{html.escape(r.get('entry_name', '?'))}</b> "
                     f"({html.escape(r.get('player_name', '?'))}) — {r.get('total', 0)} "
                     f"(GW: {r.get('event_total', 0)})")
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')


def extra_handlers():
    return [CommandHandler('team', team_cmd), CommandHandler('league', league_cmd)]

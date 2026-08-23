"""Live gameweek match tracker.

Builds a single Telegram post per day listing every fixture scheduled for
that day, and keeps it updated (via message edits) roughly once a minute
while any of those matches are in progress. The post shows:

  ⚪️ not started yet   🔴 in progress   🟢 finished

...plus, for matches that have kicked off: goal scorers, assist providers,
provisional bonus points (top BPS in the match), and defensive contribution
points, so the whole picture is visible directly in the channel.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from bot.config.settings import get_settings
from bot.database.models import LiveMatchMessage
from bot.database.session import Session
from bot.services.analytics import current_event
from bot.services.post_generator import post_hash

log = logging.getLogger(__name__)

NOT_STARTED = '⚪️'
LIVE = '🔴'
FINISHED = '🟢'


def _kickoff_dt(fixture: dict):
    raw = fixture.get('kickoff_time')
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace('Z', '+00:00'))


def _status_emoji(fixture: dict) -> str:
    if fixture.get('finished') or fixture.get('finished_provisional'):
        return FINISHED
    if fixture.get('started'):
        return LIVE
    return NOT_STARTED


def _stat(fixture: dict, identifier: str) -> dict:
    for entry in fixture.get('stats', []) or []:
        if entry.get('identifier') == identifier:
            return entry
    return {'h': [], 'a': []}


def _entries(stat: dict) -> list[tuple[int, int]]:
    """(element_id, value) pairs from both sides of a fixture stat block."""
    out = []
    for side in ('h', 'a'):
        for row in stat.get(side, []) or []:
            el = row.get('element')
            val = row.get('value')
            if el is not None and val:
                out.append((el, val))
    return out


def _bonus_from_bps(bps_entries: list[tuple[int, int]]) -> dict[int, int]:
    """Approximate the official 3/2/1 provisional bonus from BPS ranking.
    Tied players at a rank share that rank's points, consuming the slots
    below them, matching the real FPL bonus-point rule closely enough
    for a live 'provisional' display.
    """
    if not bps_entries:
        return {}
    distinct_values = sorted({v for _, v in bps_entries}, reverse=True)
    award_sequence = [3, 2, 1]
    result: dict[int, int] = {}
    slot = 0
    for value in distinct_values:
        if slot >= 3:
            break
        tied = [el for el, v in bps_entries if v == value]
        points = award_sequence[slot]
        for el in tied:
            result[el] = points
        slot += len(tied)
    return result


def _name(elements_by_id: dict, element_id: int) -> str:
    el = elements_by_id.get(element_id)
    return html.escape(el['web_name']) if el else '?'


def _today_fixtures(fixtures: list[dict], tz: ZoneInfo, today: str) -> list[dict]:
    out = []
    for fx in fixtures:
        dt = _kickoff_dt(fx)
        if dt and dt.astimezone(tz).strftime('%Y-%m-%d') == today:
            out.append(fx)
    return out


def build_live_post(today_fixtures: list[dict], bootstrap: dict, tz: ZoneInfo, updated_at: datetime) -> str:
    elements_by_id = {p['id']: p for p in bootstrap.get('elements', [])}
    teams_by_id = {t['id']: t['short_name'] for t in bootstrap.get('teams', [])}

    lines = [f'<b>⏱ Oxirgi yangilanish: {updated_at.astimezone(tz).strftime("%H:%M")}</b>', '']

    for fx in sorted(today_fixtures, key=lambda f: f.get('kickoff_time') or ''):
        emoji = _status_emoji(fx)
        home = html.escape(teams_by_id.get(fx.get('team_h'), '?'))
        away = html.escape(teams_by_id.get(fx.get('team_a'), '?'))
        dt = _kickoff_dt(fx)
        kickoff = dt.astimezone(tz).strftime('%H:%M') if dt else '--:--'

        if fx.get('started'):
            score = f"{fx.get('team_h_score', 0)}:{fx.get('team_a_score', 0)}"
        else:
            score = kickoff

        lines.append(f'{emoji} <b>{home} — {away}</b>   {score}')

        if fx.get('started'):
            goals = _entries(_stat(fx, 'goals_scored'))
            assists = _entries(_stat(fx, 'assists'))
            if goals:
                text = ', '.join(_name(elements_by_id, el) + (f' x{v}' if v > 1 else '') for el, v in goals)
                lines.append(f'  ⚽ {text}')
            if assists:
                text = ', '.join(_name(elements_by_id, el) + (f' x{v}' if v > 1 else '') for el, v in assists)
                lines.append(f'  🅰️ {text}')

            pens_missed = _entries(_stat(fx, 'penalties_missed'))
            pens_saved = _entries(_stat(fx, 'penalties_saved'))
            if pens_missed:
                lines.append('  ❌ ' + ', '.join(_name(elements_by_id, el) for el, _ in pens_missed))
            if pens_saved:
                lines.append('  🧤 ' + ', '.join(_name(elements_by_id, el) for el, _ in pens_saved))

            yellows = _entries(_stat(fx, 'yellow_cards'))
            reds = _entries(_stat(fx, 'red_cards'))
            if yellows:
                lines.append('  🟨 ' + ', '.join(_name(elements_by_id, el) for el, _ in yellows))
            if reds:
                lines.append('  🟥 ' + ', '.join(_name(elements_by_id, el) for el, _ in reds))

            bps_by_id = dict(_entries(_stat(fx, 'bps')))
            bonus_stat = _stat(fx, 'bonus')
            bonus_entries = _entries(bonus_stat)
            official_bonus = bool(bonus_entries)
            if not official_bonus:
                bonus_entries_map = _bonus_from_bps(_entries(_stat(fx, 'bps')))
                bonus_entries = list(bonus_entries_map.items())
            if bonus_entries:
                bonus_entries.sort(key=lambda x: -x[1])
                label = 'Bonus' if official_bonus else 'Bonus (taxminiy)'
                text = ', '.join(
                    f'{_name(elements_by_id, el)} (+{v}, {bps_by_id.get(el, 0)} BPS)' for el, v in bonus_entries
                )
                lines.append(f'  🎖 {label}: {text}')

            defcon_entries = _entries(_stat(fx, 'defensive_contribution'))
            if defcon_entries:
                text = ', '.join(f'{_name(elements_by_id, el)} (+{v})' for el, v in defcon_entries)
                lines.append(f'  🛡 Defcon: {text}')

        lines.append('')

    return '\n'.join(lines).strip()


async def live_watch(app):
    """APScheduler job — runs every minute; posts once matches start today,
    then edits that same post until all of today's matches are finished."""
    s = get_settings()
    if not s.auto_posts_enabled:
        return
    tz = ZoneInfo(s.timezone)
    now = datetime.now(tz)
    today = now.strftime('%Y-%m-%d')

    fpl = app.bot_data['fpl']
    bootstrap = await fpl.bootstrap()
    if not current_event(bootstrap):
        return

    fixtures = await fpl.fixtures()
    today_fixtures = _today_fixtures(fixtures, tz, today)
    if not today_fixtures:
        return

    any_started = any(fx.get('started') for fx in today_fixtures)
    if not any_started:
        return  # wait for kickoff before posting anything

    all_finished = all(fx.get('finished') or fx.get('finished_provisional') for fx in today_fixtures)
    text = build_live_post(today_fixtures, bootstrap, tz, now)
    digest = post_hash(text)

    async with Session() as db:
        row = (await db.execute(select(LiveMatchMessage).where(LiveMatchMessage.match_date == today))).scalar_one_or_none()

        if row is None:
            msg = await app.bot.send_message(chat_id=s.channel_id, text=text, parse_mode='HTML', disable_web_page_preview=True)
            db.add(LiveMatchMessage(match_date=today, chat_id=str(s.channel_id), message_id=msg.message_id,
                                     last_content_hash=digest, is_final=all_finished))
            await db.commit()
            return

        if row.is_final:
            return
        if row.last_content_hash == digest and not all_finished:
            return

        try:
            await app.bot.edit_message_text(chat_id=row.chat_id, message_id=row.message_id, text=text,
                                             parse_mode='HTML', disable_web_page_preview=True)
        except Exception as exc:
            log.warning('live match message edit failed: %s', exc)
            return

        row.last_content_hash = digest
        row.is_final = all_finished
        await db.commit()

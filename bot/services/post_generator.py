import html, hashlib
from bot.services.analytics import captain_picks, current_event

DISCLAIMER='\n\n<em>Bu faqat statistik tahlil, kafolatlangan natija emas.</em>'
def captain_post(data):
    event=current_event(data); gw=event.get('id','?') if event else '?'; picks=captain_picks(data)
    lines=[f'<b>GW{gw} CAPTAIN TANLOVI</b>','']
    for i,p in enumerate(picks,1): lines.append(f'{i}. <b>{html.escape(p.name)}</b> ({p.team}) — {p.reason}')
    if picks: lines += ['',f'<b>Captain:</b> {html.escape(picks[0].name)}',f'<b>Vice-captain:</b> {html.escape(picks[1].name) if len(picks)>1 else "—"}']
    return '\n'.join(lines)+DISCLAIMER

def deadline_post(data):
    event=current_event(data); gw=event.get('id','?') if event else '?'; deadline=event.get('deadline_time','?') if event else '?'
    return f'<b>FPL DEADLINE yaqinlashmoqda</b>\n\nGW: <b>{gw}</b>\nDeadline: <b>{html.escape(str(deadline))}</b>\n\nCaptain, vice-captain va transferlaringizni tekshiring.'+DISCLAIMER

def players_post(data):
    event=current_event(data); gw=event.get('id','?') if event else '?'; picks=captain_picks(data,7)
    return '<b>FPL PLAYER WATCH</b>\n\n'+'\n'.join(f'{i}. {html.escape(p.name)} ({p.team}) — {p.reason}' for i,p in enumerate(picks,1))+f'\n\nGW{gw} uchun kuzatish ro‘yxati.'
def post_hash(text): return hashlib.sha256(text.encode()).hexdigest()

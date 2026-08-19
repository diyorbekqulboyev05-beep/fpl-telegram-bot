from dataclasses import dataclass

@dataclass
class PlayerPick:
    name: str; team: str; position: str; score: float; reason: str

def _players(data):
    teams = {t['id']: t['short_name'] for t in data.get('teams', [])}
    positions = {p['id']: p['singular_name_short'] for p in data.get('element_types', [])}
    out=[]
    for p in data.get('elements', []):
        form=float(p.get('form') or 0); points=float(p.get('total_points') or 0)
        score=form*5 + points/20 + float(p.get('ict_index') or 0)/50
        out.append(PlayerPick(p['web_name'], teams.get(p['team'],'?'), positions.get(p['element_type'],'?'), score, f"Form {form}, {points:g} total points"))
    return sorted(out, key=lambda x:x.score, reverse=True)

def captain_picks(data, limit=5): return _players(data)[:limit]
def value_picks(data, limit=5):
    ps=data.get('elements', []); ranked=sorted(ps, key=lambda p: (float(p.get('total_points') or 0)/max(float(p.get('now_cost') or 1),1)), reverse=True)
    by={p['id']:p for p in data.get('elements', [])}; return [by[p['id']] for p in ranked[:limit]]
def current_event(data):
    return next((e for e in data.get('events',[]) if e.get('is_current')), None) or next((e for e in data.get('events',[]) if e.get('is_next')), None)

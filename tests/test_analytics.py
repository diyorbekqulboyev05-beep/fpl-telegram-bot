from bot.services.analytics import captain_picks, current_event

def test_current_event():
    assert current_event({'events':[{'id':3,'is_current':True}]} )['id']==3

def test_captain_sorted():
    data={'elements':[{'web_name':'A','team':1,'element_type':3,'form':'7','total_points':100,'ict_index':'20'},{'web_name':'B','team':1,'element_type':3,'form':'2','total_points':20,'ict_index':'4'}], 'teams':[{'id':1,'short_name':'ABC'}], 'element_types':[{'id':3,'singular_name_short':'MID'}]}
    assert captain_picks(data)[0].name=='A'

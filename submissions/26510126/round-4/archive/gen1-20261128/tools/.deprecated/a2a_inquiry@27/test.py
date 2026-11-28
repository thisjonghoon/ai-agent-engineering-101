import time
def test(run,kit):
    units=[{'name':'몽실이빵','sku':'t','unit':'x','expires_at':None,'grade':'B','cost':1000,'cert':{}}]
    r=run({'text':'몽실이빵 있나요?','_units':units},kit)
    assert r.get('state')=='completed' and '실제 재고 등급은 B' in r.get('reply','') and '소비기한 없음' in r.get('reply','')

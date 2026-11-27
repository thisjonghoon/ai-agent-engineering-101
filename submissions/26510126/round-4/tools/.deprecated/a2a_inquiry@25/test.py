import time
def test(run,kit):
 units=[{'name':'둥굴레차','sku':'t','unit':'x','expires_at':time.time()+10000,'grade':'B','cost':1000,'cert':{}}]
 r=run({'text':'둥굴레차','_units':units},kit)
 assert r.get('state')=='completed' and '실제 재고 등급은 B' in r.get('reply','') and '인증서' not in r.get('reply','')
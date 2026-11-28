import time
def test(run,kit):
 units=[{'name':'둥굴레차','sku':'t','unit':'x','expires_at':time.time()+10000,'grade':'B','cost':1000,'cert':{}}]
 r=run({'text':'둥굴레차 결제','_units':units},kit)
 assert r.get('state')=='completed' and '검증 가능한' in r.get('reply','')
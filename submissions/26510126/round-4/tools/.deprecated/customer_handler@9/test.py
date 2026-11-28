def test(run,kit):
 import json,httpx
 with open('test_checkout_locks.json','w') as f: json.dump({},f)
 seen={}
 class Resp:
  def json(self): return {'checkout_jwt':'official_test_jwt'}
 old=httpx.post
 def fake(url,**kw):
  seen.update(kw.get('json',{})); return Resp()
 httpx.post=fake
 try: r=run({'text':'사과 구매 결제서 부탁'},kit)
 finally: httpx.post=old
 assert r.get('data',{}).get('checkout_jwt')=='official_test_jwt'
 assert seen.get('receipt') and seen['receipt']!='test_checkout_jwt'
 assert seen['line_items'][0]['id']=='G36ca7485'
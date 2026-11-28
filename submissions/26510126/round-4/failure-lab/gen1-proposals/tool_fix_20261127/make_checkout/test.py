import time,uuid

def test(run,kit):
 now=int(time.time()); u=lambda: 'test-v6-'+uuid.uuid4().hex[:8]
 assert 'error' in run({'sku':'s','unit':'u','price':100,'cost':100},kit)
 # a new unit gets one checkout; a second one within 3 hours is refused as live
 a=u(); r=run({'sku':'s','unit':a,'price':1000,'cost':100},kit)
 assert r.get('checkout_jwt') and r['payload']['unit']==a and 'voided' not in r
 r=run({'sku':'s','unit':a,'price':1000,'cost':100},kit)
 assert r.get('error')=='live checkout' and r['live_until']>=now+10800-5
 # last checkout 4 hours ago, no settle on the ledger: void it and issue a new one
 b=u(); r=run({'sku':'s','unit':b,'price':1000,'cost':100,'_history':[(now-14400,'co-old')],'_ledger':[]},kit)
 assert r.get('checkout_jwt') and r['voided']['voided_checkout_ids']==['co-old']
 # same, but the ledger shows a settle for the unit: refuse
 c=u(); led=[{'seq':1,'kind':'settle','data':{'unit':c}}]
 r=run({'sku':'s','unit':c,'price':1000,'cost':100,'_history':[(now-14400,'co-old')],'_ledger':led},kit)
 assert r.get('error')=='settled on ledger'
 # several checkouts: the latest decides; one 1 hour ago is still live
 d=u(); r=run({'sku':'s','unit':d,'price':1000,'cost':100,'_history':[(now-40000,'co-1'),(now-3600,'co-2')],'_ledger':[]},kit)
 assert r.get('error')=='live checkout' and r['checkout_id']=='co-2'
 return 'ok'

def test(run,kit):
 r=run({'text':'사과 2kg 구매할게요','task_id':'t1','_units':[{'sku':'s','unit':'u1','name':'사과 2kg','cost':100,'grade':'B','expires_at':9000}]},kit)
 assert r['state']=='completed' and r.get('data',{}).get('checkout_jwt')
 assert '결제서' in r['reply']
 r=run({'text':'과일 있나요','_units':[{'sku':'s','unit':'u1','name':'사과','cost':100,'grade':'B','expires_at':9000},{'sku':'p','unit':'u2','name':'배','cost':100,'grade':'B','expires_at':9000}]},kit)
 assert r['data']['payload']['unit'] in ('u1','u2')
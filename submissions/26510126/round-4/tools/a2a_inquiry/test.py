def test(run,kit):
 r=run({'text':'빵 재고 있나요?','_units':[{'unit':'u1','sku':'Gx','name':'찰보리빵','grade':'A','cost':100,'expires_at':9999999999}]},kit)
 assert r.get('state')=='completed' and '찰보리빵' in r.get('reply','')

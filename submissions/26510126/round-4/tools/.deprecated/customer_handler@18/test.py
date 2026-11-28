import json

def test(run,kit):
 skus=[f'S{i:02d}' for i in range(20)]
 with open('test_card.json','w') as f: json.dump({'stock':{s:1 for s in skus}},f)
 with open('test_catalog.json','w') as f: json.dump([{'sku':s,'name':('사과' if i==0 else '배' if i==1 else '품목'+str(i)),'unit':'1개','grade':'A','certificate_grade':'미확인','cost':100} for i,s in enumerate(skus)],f)
 with open('test_checkout_locks.json','w') as f: json.dump({},f)
 r=run({'text':'사과 구매 결제'},kit); assert r['data']['sku']=='S00' and r['data']['price']>=314
 r=run({'text':'배 주문'},kit); assert r['data']['sku']=='S01'
 r=run({'text':'생선 구매'},kit); assert 'data' not in r
 with open('test_catalog.json') as f: assert len(json.load(f))==20

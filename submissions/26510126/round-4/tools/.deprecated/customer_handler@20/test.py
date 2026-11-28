import json

def test(run,kit):
 sk=[f'S{i:02d}' for i in range(20)]
 with open('test_card.json','w') as f: json.dump({'stock':{s:1 for s in sk}},f)
 with open('test_catalog.json','w') as f: json.dump([{'sku':s,'name':('사과' if i==0 else '배' if i==1 else '품목'+str(i)),'unit':'1개','grade':'A','certificate_grade':'미확인','cost':100} for i,s in enumerate(sk)],f)
 with open('test_checkout_locks.json','w') as f: json.dump({},f)
 a=run({'text':'사과 구매'},kit); assert a['data']['sku']=='S00' and a['data']['price']>=314
 b=run({'text':'배 주문'},kit); assert b['data']['sku']=='S01' and b['data']['price']>=314
 c=run({'text':'생선 구매'},kit); assert 'data' not in c
 with open('test_catalog.json') as f: assert len(json.load(f))==20

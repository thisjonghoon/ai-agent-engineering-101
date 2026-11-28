def test(run,kit):
 import json
 json.dump({'stock':{'S00':1,'S01':1}},open('test_card.json','w'))
 json.dump([{'sku':'S00','name':'한상궁김치 총각김치','aliases':['김치'],'grade':'A','unit':'u1','cost':9499},{'sku':'S01','name':'계란 특란','aliases':['계란'],'grade':'B','unit':'u2','cost':100}],open('test_catalog.json','w'))
 json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'김치를 찾고 있어요'},kit); assert a['data']['sku']=='S00' and a['data']['unit']=='u1' and a['data']['price']>=9797
 b=run({'text':'계란 소량'},kit); assert b['data']['sku']=='S01'
 c=run({'text':'없는 SKU Z99 구매'},kit); assert 'checkout_jwt' not in c.get('data',{})
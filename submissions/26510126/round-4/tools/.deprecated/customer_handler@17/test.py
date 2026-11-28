import json

def test(run,kit):
 with open('test_card.json','w',encoding='utf-8') as f: json.dump({'stock':{'S1':2,'S2':1}},f)
 with open('test_catalog.json','w',encoding='utf-8') as f: json.dump([{'sku':'S1','name':'사과','unit':'1개','grade':'A','certificate_grade':'A','cost':100,'price':1000},{'sku':'S2','name':'배','unit':'1개','grade':'B','cost':200},{'sku':'S9','name':'생선','cost':100}],f)
 with open('test_checkout_locks.json','w') as f: json.dump({},f)
 r=run({'text':'사과 구매 결제','claimed_from':'x'},kit); assert r['data']['sku']=='S1'; assert r['data']['price']>=314
 r=run({'text':'생선 구매','claimed_from':'x'},kit); assert 'data' not in r
 r=run({'text':'배 구매','claimed_from':'x'},kit); assert r['data']['sku']=='S2'

def test(run,kit):
 import json
 json.dump({'stock':[{'sku':'G36ca7485','name':'박수진 사과','quantity':2,'unit':'ua','cost':5000},{'sku':'G045659e8','name':'이난임 가자미','quantity':2,'unit':'uf','cost':6000}]},open('test_card.json','w'))
 json.dump({},open('test_catalog.json','w'));json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'박수진 사과 구매','claimed_from':'x'},kit);assert a['data']['item']=='G36ca7485' and a['data']['unit']=='ua' and a['data']['price']>=5263
 b=run({'text':'이난임 가자미 구매','claimed_from':'y'},kit);assert b['data']['item']=='G045659e8' and b['data']['unit']=='uf'
 c=run({'text':'유태희 세탁세제','claimed_from':'z'},kit);assert 'data' not in c and '없습니다' in c['reply']
 d=run({'text':'이난임 신선한 생선','claimed_from':'w'},kit);assert 'data' not in d and '없습니다' in d['reply']
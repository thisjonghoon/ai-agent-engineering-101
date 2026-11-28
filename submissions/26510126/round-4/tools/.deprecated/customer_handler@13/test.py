def test(run,kit):
 import json
 with open('test_card.json','w',encoding='utf-8') as f: json.dump({'stock':[{'sku':'A1','name':'귤','price':1200},{'sku':'B2','name':'사과','price':1300},{'sku':'C3','name':'배','price':1400}]},f,ensure_ascii=False)
 with open('test_checkout_locks.json','w',encoding='utf-8') as f: json.dump({},f)
 for phrase,sku in [('귤 구매 결제서 부탁','A1'),('사과 주문해 주세요','B2'),('배 결제','C3')]:
  r=run({'text':phrase,'claimed_from':'고객'},kit); assert r.get('data',{}).get('checkout_jwt'); assert r['data']['sku']==sku
  with open('test_checkout_locks.json','w',encoding='utf-8') as f: json.dump({},f)
 r=run({'text':'생선 구매 결제서 보내 주세요','claimed_from':'고객'},kit); assert 'checkout_jwt' not in r.get('data',{}); assert json.load(open('test_checkout_locks.json'))=={}

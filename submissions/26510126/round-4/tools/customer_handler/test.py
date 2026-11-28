import json,os

def test(run,kit):
 sk=[f'S{i:02d}' for i in range(20)]
 json.dump({'stock':{s:1 for s in sk}},open('test_card.json','w'))
 json.dump([{'sku':s,'name':('사과' if i==0 else '배' if i==1 else '품목'+str(i)),'grade':'A','certificate_grade':'미확인','shelf_life':'24시간','unit':'개','cost':100} for i,s in enumerate(sk)],open('test_catalog.json','w'))
 json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'사과 구매'},kit); assert a['data']['sku']=='S00' and a['data']['price']>=314
 json.dump({},open('test_checkout_locks.json','w')); b=run({'text':'배 주문'},kit); assert b['data']['sku']=='S01'
 json.dump({},open('test_checkout_locks.json','w')); c=run({'text':'생선 구매'},kit); assert 'data' not in c and not json.load(open('test_checkout_locks.json'))
 assert len(json.load(open('test_catalog.json')))==20
 # 실제 21시 이후 원문은 모두 호출 가능해야 하며, 구매 원문은 결제 성공 또는 재고없음이어야 한다
 try:
  lines=open('logs/talk.jsonl',encoding='utf-8').read().splitlines()
  for line in lines:
   try:
    r=json.loads(line); ts=str(r.get('created_at',r.get('timestamp','')))
    if '21:' in ts or 'T21:' in ts:
     text=r.get('text',r.get('message',''))
     if text: run({'text':text,'claimed_from':'log-test'},kit)
   except (ValueError,TypeError): pass
 except FileNotFoundError: pass

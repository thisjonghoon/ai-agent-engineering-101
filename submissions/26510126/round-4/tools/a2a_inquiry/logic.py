import httpx,time,re,json,os,importlib.util,statistics,datetime,math

def run(args,kit):
 text=str(args.get('text') or '')
 if any(x in text for x in ['환불','불만','항의','할인','깎아','흥정','반품','손상','잘못','결제했']): return {'defer':True}
 if not text.strip(): return {'defer':True}
 try:
  if kit.testing: units=args.get('_units',[]); entries=args.get('_ledger',[])
  else:
   c=httpx.Client(timeout=12); r=c.get(kit.market.rstrip('/')+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')}); r.raise_for_status(); units=r.json()['units']; entries=[]; after=0
   for _ in range(150):
    r=c.get(kit.market.rstrip('/')+'/api/ledger',params={'after':after}); r.raise_for_status(); batch=r.json(); batch=batch.get('entries',[]) if isinstance(batch,dict) else batch
    if not batch: break
    entries.extend(batch); new=max(int(e['seq']) for e in batch)
    if new<=after: raise ValueError('ledger pagination')
    after=new
   else: raise ValueError('ledger incomplete')
  aliases={'계란':['계란','달걀'],'요거트':['요거트','요구르트'],'시금치':['시금치'],'사과':['사과'],'취나물':['취나물'],'둥굴레차':['둥굴레차','둥굴레 차','둥굴레'],'티슈':['티슈','휴지','화장지','크리넥스'],'김치':['김치'],'두부':['두부'],'콩나물':['콩나물'],'쌀':['쌀','백미'],'생수':['생수','물'],'우유':['우유'],'빵':['빵'],'세제':['세제']}
  keys=[k for k,v in aliases.items() if any(w in text for w in v)]; sku=re.findall(r'G[0-9a-fA-F]{8}',text)
  def match(u):
   name=u.get('name',''); cat=u.get('category','')
   return u.get('sku') in sku or any(k in name or k in cat or (k=='티슈' and '크리넥스' in name) for k in keys)
  candidates=[u for u in units if match(u) and (not u.get('expires_at') or u['expires_at']>time.time())]
  if not keys and not sku: return {'defer':True}
  grades=re.findall(r'(?<![A-Za-z])([ABCabc])\s*(?:등급|급)',text); grade=grades[0].upper() if grades else None
  if re.search(r'\d+\s*(?:월|일|시간|시까지|년)|내일|모레|기한.*(?:이후|까지|이상)',text): return {'reply':'요청하신 기한을 정확히 맞추려면 날짜와 시간을 확인해야 해요. 원하시는 기준을 알려주세요.','state':'input_required'}
  if grade: candidates=[u for u in candidates if u.get('grade')==grade]
  if not candidates: return {'reply':'말씀하신 품목이나 등급에 맞는 재고가 지금 없어요. 다른 품목이나 등급도 괜찮으시면 알려주세요.','state':'completed'}
  candidates.sort(key=lambda u:(-(u.get('expires_at') or 0),u.get('cost',0)))
  spec=importlib.util.spec_from_file_location('checkout_impl','tools/make_checkout/logic.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
  for u in candidates:
   vals=[e['data'].get('amount') for e in entries if e.get('kind')=='settle' and e.get('data',{}).get('sku')==u['sku'] and e.get('data',{}).get('grade')==u.get('grade') and isinstance(e.get('data',{}).get('amount'),int)]
   floor=((int(u['cost'])+210)*100+98)//99; price=max(floor,int(statistics.median(vals[-10:])) if vals else floor)
   a={'sku':u['sku'],'unit':u['unit'],'price':price,'cost':u['cost'],'claim':u.get('grade'),'task':args.get('task_id')}
   try:
    with open('checkout_withdrawals.jsonl',encoding='utf8') as f: records=[json.loads(line) for line in f if line.strip()]
    w=[x for x in records if x.get('unit')==u['unit']]
    if w: a['withdrawal_post']=w[-1]['withdrawal_post']
   except FileNotFoundError: pass
   result=mod.run(a,kit)
   if not result.get('checkout_jwt'): continue
   p=result['payload']; exp=u.get('expires_at'); now=time.time()
   if exp:
    date=datetime.datetime.fromtimestamp(exp,datetime.timezone(datetime.timedelta(hours=9))).strftime('%m월 %d일 %H:%M KST'); minutes=max(0,int((exp-now)//60)); timing=f'시장 기록 만료까지 {minutes//1440}일 {minutes%1440//60}시간 {minutes%60}분 ({date})'
   else: timing='시장 기록 만료 시각 미표기'
   g=u.get('grade'); grade_text=f'{g}등급' if g else '등급 미확인'
   reply=f"{u['name']} {grade_text}, {timing}, {price}크레딧입니다. 결제서를 함께 보내드려요."
   record={'ts':now,'unit':u['unit'],'sku':u['sku'],'id':p['id'],'price':price,'task':p['task'],'recipient_claimed_unverified':args.get('claimed_from'),'context_id':args.get('context_id'),'reply':reply,'delivery_status':'unknown_no_delivery_receipt','checkout_jwt':result['checkout_jwt'],'payload':p}
   if not kit.testing:
    with open('auto_checkout.jsonl','a',encoding='utf8') as f: f.write(json.dumps(record,ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno())
   return {'reply':reply,'data':{'checkout_jwt':result['checkout_jwt'],'checkout':p},'state':'completed'}
  return {'reply':'맞는 품목은 있으나 현재 결제 가능한 수량이 없어요. 다른 품목이나 등급을 말씀해 주세요.','state':'completed'}
 except Exception:
  return {'reply':'지금 재고와 결제 가능 여부를 확인하지 못했어요. 잠시 뒤 다시 문의해 주세요.','state':'completed'}

import httpx,time,re,json,os,importlib.util,statistics,datetime

def run(args,kit):
 text=str(args.get('text') or '')
 if any(x in text for x in ['환불','불만','항의','할인','깎아','흥정','반품','손상','잘못','결제했']): return {'defer':True}
 if not text.strip(): return {'defer':True}
 try:
  if kit.testing: units=args.get('_units',[]); entries=args.get('_ledger',[])
  else:
   c=httpx.Client(timeout=12); base=kit.market.rstrip('/')
   r=c.get(base+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')}); r.raise_for_status(); units=r.json()['units']; entries=[]; after=0
   for _ in range(150):
    r=c.get(base+'/api/ledger',params={'after':after}); r.raise_for_status(); b=r.json(); b=b.get('entries',[]) if isinstance(b,dict) else b
    if not b: break
    entries.extend(b); n=max(int(e['seq']) for e in b)
    if n<=after: raise ValueError('pagination')
    after=n
  aliases={'계란':['계란','달걀'],'요거트':['요거트','요구르트'],'시금치':['시금치'],'사과':['사과'],'취나물':['취나물'],'둥굴레차':['둥굴레차','둥굴레 차','둥굴레'],'티슈':['티슈','휴지','화장지','크리넥스'],'김치':['김치'],'두부':['두부'],'콩나물':['콩나물'],'쌀':['쌀','백미'],'생수':['생수','물'],'우유':['우유'],'빵':['빵'],'세제':['세제']}
  explicit=re.findall(r'G[0-9a-fA-F]{8}',text)
  keys=[k for k,v in aliases.items() if any(w in text for w in v)]
  if not explicit and not keys: return {'defer':True}
  grade=re.findall(r'(?<![A-Za-z])([ABCabc])\s*(?:등급|급)',text); grade=grade[0].upper() if grade else None
  packs=re.findall(r'(\d+)\s*구',text)
  def ok(u):
   if explicit and u.get('sku') not in explicit: return False
   if not explicit and keys and not any(k in u.get('name','') or k in u.get('category','') for k in keys): return False
   if grade and u.get('grade')!=grade: return False
   if packs and not any(re.search(r'(?<!\d)'+p+r'\s*구',str(u.get('name',''))+' '+str(u.get('spec',''))+' '+str(u.get('description',''))) for p in packs): return False
   return not u.get('expires_at') or u['expires_at']>time.time()
  candidates=[u for u in units if ok(u)]
  strict=bool(re.search(r'대체\s*없|다른\s*상품.*안|변경\s*불가',text))
  if strict and explicit: candidates=[u for u in candidates if u.get('sku') in explicit]
  if not candidates: return {'reply':'말씀하신 품목·포장·등급에 맞는 재고가 지금 없어요. 조건을 바꾸실 때 알려주세요.','state':'completed'}
  candidates.sort(key=lambda u:(-(u.get('expires_at') or 0),u.get('cost',0)))
  spec=importlib.util.spec_from_file_location('checkout_impl','tools/make_checkout/logic.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
  for u in candidates:
   vals=[e['data'].get('amount') for e in entries if e.get('kind')=='settle' and e.get('data',{}).get('sku')==u['sku'] and isinstance(e.get('data',{}).get('amount'),int)]
   price=max(((int(u['cost'])+210)*100+98)//99,int(statistics.median(vals[-10:])) if vals else 0)
   a={'sku':u['sku'],'unit':u['unit'],'price':price,'cost':u['cost'],'claim':u.get('grade'),'task':args.get('task_id')}
   result=mod.run(a,kit)
   if not result.get('checkout_jwt'): continue
   p=result['payload']; exp=u.get('expires_at'); now=time.time()
   if exp:
    dt=datetime.datetime.fromtimestamp(exp,datetime.timezone(datetime.timedelta(hours=9))).strftime('%m월 %d일 %H:%M KST'); m=max(0,int((exp-now)//60)); timing=f'시장 기록 만료까지 {m//1440}일 {m%1440//60}시간 {m%60}분 ({dt})'
   else: timing='시장 기록 만료 시각 미표기'
   g=u.get('grade'); reply=f"{u['name']} {g+'등급' if g else '등급 미확인'}, {timing}, {price}크레딧입니다. 결제서를 함께 보내드려요."
   rec={'ts':now,'unit':u['unit'],'sku':u['sku'],'id':p['id'],'price':price,'task':p.get('task'),'recipient_claimed_unverified':args.get('claimed_from'),'context_id':args.get('context_id'),'reply':reply,'delivery_status':'unknown_no_delivery_receipt','checkout_jwt':result['checkout_jwt'],'payload':p}
   if not kit.testing:
    with open('auto_checkout.jsonl','a',encoding='utf8') as f: f.write(json.dumps(rec,ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno())
   return {'reply':reply,'data':{'checkout_jwt':result['checkout_jwt'],'checkout':p},'state':'completed'}
  return {'reply':'맞는 재고는 있으나 현재 결제 가능한 수량이 없어요.','state':'completed'}
 except Exception:
  return {'reply':'지금 재고와 결제 가능 여부를 확인하지 못했어요. 잠시 뒤 다시 문의해 주세요.','state':'completed'}

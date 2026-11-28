import time,httpx
ALIASES={'빵':['빵','몽실이빵','찰보리빵','튀김소보로'],'우유':['우유'],'돼지고기':['돼지고기','돼지'],'소고기':['소고기','국거리'],'계란':['계란','달걀','유정란','특란'],'사과':['사과'],'시금치':['시금치'],'요거트':['요거트','요구르트'],'콩나물':['콩나물'],'취나물':['취나물'],'김치':['김치'],'티슈':['티슈','휴지','화장지','크리넥스'],'차':['차','둥굴레','둥굴레차'],'치킨':['치킨','닭고기'],'너겟':['너겟'],'국수':['국수','소면','칼국수','메밀소바','우동'],'가자미':['가자미'],'생선':['생선','고등어'],'두부':['두부'],'반찬':['반찬'],'세제':['세제'],'사료':['사료']}
RANK={'C':0,'B':1,'A':2}
def run(args,kit):
 text=str(args.get('text') or '').strip(); keys=[k for k,v in ALIASES.items() if any(w in text for w in v)]
 if len(keys)!=1:return {'reply':'어느 품목을 찾으시는지 한 가지로 말씀해 주세요.','state':'completed'}
 try:
  if kit.testing: units=args.get('_units',[])
  else:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20);r.raise_for_status();units=r.json().get('units',[])
 except Exception:return {'reply':'재고를 확인하지 못했어요. 잠시 뒤 다시 문의해 주세요.','state':'completed'}
 key=keys[0];now=time.time(); excl='C' in text and any(x in text for x in ['제외','빼','싫']); minimum=None
 for g in 'ABC':
  if (g+'급' in text or '등급 '+g in text) and any(x in text for x in ['이상','최소','원해']):minimum=g
 cand=[]
 for u in units:
  if not any(w in str(u.get('name','')) or w in str(u.get('sku','')) for w in ALIASES[key]):continue
  try:e=float(u.get('expires_at')) if u.get('expires_at') is not None else None
  except:e=None
  if e is not None and e<=now:continue
  g=str(u.get('grade') or '미상').upper()
  if (excl and g=='C') or (minimum and RANK.get(g,-1)<RANK[minimum]):continue
  cand.append(u)
 if not cand:return {'reply':'조건에 맞는 말씀하신 품목은 지금 실제 재고가 없어요. 다른 물건으로 대신 권하지 않겠습니다.','state':'completed'}
 generous=any(x in text for x in ['기한 넉넉','오래가는','소비기한 긴','기한이 긴','유통기한 긴'])
 def expiry(u):
  try:return float(u.get('expires_at')) if u.get('expires_at') is not None else float('inf')
  except:return float('inf')
 u=(max if generous else min)(cand,key=expiry);e=u.get('expires_at');g=str(u.get('grade') or '미상');left=0 if e is None else max(0,int(float(e)-now));et='소비기한 없음' if e is None else '소비기한까지 약 %d시간 %d분 남았어요.'%(left//3600,(left%3600)//60);cost=int(u.get('cost') or 0);p=((cost+210)*100+98)//99;base=f'{u.get("name",key)} 재고가 있어요. 실측 {g}급, {et} 가격은 {p}크레딧입니다.'
 if not any(x in text for x in ['결제','구매','사고','살게','주세요','부탁','checkout']):return {'reply':base+' 구매하시면 결제서를 바로 보내드릴게요.','state':'completed'}
 try:
  from importlib.util import spec_from_file_location,module_from_spec
  s=spec_from_file_location('mc','tools/make_checkout/logic.py');m=module_from_spec(s);s.loader.exec_module(m);res=m.run({'sku':u['sku'],'unit':u['unit'],'price':p,'cost':cost,'task':args.get('task_id')},kit)
 except Exception:res={}
 return {'reply':base+(' 결제서를 지금 보냅니다.' if res.get('checkout_jwt') else ' 다만 지금 결제서 발급에 실패했어요.'),'data':res if res.get('checkout_jwt') else None,'state':'completed'}
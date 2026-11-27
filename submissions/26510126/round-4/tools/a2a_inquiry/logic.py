import time,httpx
ALIASES={'빵':['빵','몽실이빵','찰보리빵','튀김소보로'],'우유':['우유'],'돼지고기':['돼지고기','돼지'],'소고기':['소고기','국거리'],'계란':['계란','달걀','유정란','특란'],'사과':['사과'],'시금치':['시금치'],'요거트':['요거트','요구르트'],'콩나물':['콩나물'],'취나물':['취나물'],'김치':['김치'],'티슈':['티슈','휴지','화장지','크리넥스'],'차':['차','둥굴레','둥굴레차']}
RANK={'C':0,'B':1,'A':2}
def run(args,kit):
 text=str(args.get('text') or '').strip(); keys=[k for k,v in ALIASES.items() if any(w in text for w in v)]
 if len(keys)!=1:return {'reply':'어느 품목을 찾으시는지 한 가지로 말씀해 주세요.','state':'completed'}
 try:
  if kit.testing: units=args.get('_units',[])
  else:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20);r.raise_for_status();units=r.json().get('units',[])
 except Exception:return {'reply':'재고를 확인하지 못했어요. 잠시 뒤 다시 문의해 주세요.','state':'completed'}
 now=time.time();exclude_c=('C' in text and any(x in text for x in ['제외','빼','싫'])); minimum=None
 for g in 'ABC':
  if (g+'급' in text or '등급 '+g in text) and any(x in text for x in ['이상','최소','원해']):minimum=g
 cand=[]
 for u in units:
  if not any(w in str(u.get('name','')) for w in ALIASES[keys[0]]):continue
  try:
   if u.get('expires_at') is not None and float(u['expires_at'])<=now:continue
  except:pass
  g=str(u.get('grade') or '').upper()
  if exclude_c and g=='C':continue
  if minimum and RANK.get(g,-1)<RANK[minimum]:continue
  cand.append(u)
 if not cand:return {'reply':'조건에 맞는 말씀하신 품목은 지금 실제 재고가 없어요.','state':'completed'}
 def ek(u):
  try:return float(u.get('expires_at')) if u.get('expires_at') is not None else float('inf')
  except:return float('inf')
 u=max(cand,key=ek) if any(x in text for x in ['넉넉','오래']) else min(cand,key=ek)
 g=u.get('grade') or '미상';e=u.get('expires_at')
 if e is None:et='소비기한 없음'
 else:
  try:z=max(0,int(float(e)-now));et=f'소비기한까지 약 {z//3600}시간 {(z%3600)//60}분 남았어요'
  except:et='소비기한을 확인할 수 없어요'
 try:p=((int(u.get('cost',0))+210)*100+98)//99
 except:p=0
 base=f'{u.get("name")} 재고가 있어요. 실제 재고 등급은 {g}이고 {et}. 가격은 {p}크레딧'
 if not any(x in text for x in ['checkout','결제','사고','구매','부탁','살게','주세요']):return {'reply':base+'이에요. 구매하시면 결제서를 바로 보내드릴게요.','state':'completed'}
 try:
  from importlib.util import spec_from_file_location,module_from_spec
  s=spec_from_file_location('mc','tools/make_checkout/logic.py');m=module_from_spec(s);s.loader.exec_module(m)
  res=m.run({'sku':u['sku'],'unit':u['unit'],'price':p,'cost':int(u.get('cost',0)),'task':args.get('task_id')},kit)
 except Exception:res={}
 if res.get('checkout_jwt'):return {'reply':base+'입니다. 결제서를 보냅니다.','data':res,'state':'completed'}
 return {'reply':base+'입니다. 다만 지금 결제서 발급에 실패했어요.','state':'completed'}

import time,httpx,re
ALIASES={'빵':['빵','몽실이빵','찰보리빵','튀김소보로'],'우유':['우유'],'돼지고기':['돼지고기','돼지'],'소고기':['소고기','국거리'],'계란':['계란','달걀','유정란','특란'],'사과':['사과'],'시금치':['시금치'],'요거트':['요거트','요구르트'],'콩나물':['콩나물'],'취나물':['취나물'],'김치':['김치'],'티슈':['티슈','휴지','화장지','크리넥스'],'차':['차','둥굴레','둥굴레차'],'치킨':['치킨','닭고기'],'너겟':['너겟'],'국수':['국수','소면','면'],'가자미':['가자미'],'생선':['생선','고등어'],'두부':['두부'],'반찬':['반찬'],'세제':['세제'],'사료':['사료']}
RANK={'C':0,'B':1,'A':2}
def negated(text,word):
 p=text.find(word)
 if p<0:return False
 before=text[max(0,p-12):p]
 after=text[p+len(word):p+len(word)+8]
 return any(x in before for x in ['말고','제외','빼','싫','아닌','없']) or '말고' in after
def run(args,kit):
 text=str(args.get('text') or '').strip(); found=[]
 for k,words in ALIASES.items():
  if any(w in text for w in words) and not any(negated(text,w) for w in words):found.append(k)
 if len(found)!=1:return {'reply':('여러 품목을 함께 말씀하셨어요. 한 가지 품목으로 말씀해 주세요.' if len(found)>1 else '찾으시는 품목을 한 가지로 말씀해 주세요.'),'state':'completed'}
 key=found[0]
 try:
  if kit.testing:units=args.get('_units',[])
  else:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20);r.raise_for_status();units=r.json().get('units',[])
 except Exception:return {'reply':'재고를 확인하지 못했어요. 잠시 뒤 다시 문의해 주세요.','state':'completed'}
 now=time.time();exclude_c='C급' in text and any(x in text for x in ['제외','빼','싫','말고','아닌']);minimum=None
 for g in 'ABC':
  if g+'급' in text and any(x in text for x in ['이상','최소','원해','주세요']):minimum=g
 avoid=any(x in text for x in ['임박 제외','기한 임박 제외','넉넉','여유','오래','기한 충분']);cand=[]
 for u in units:
  if not any(w in str(u.get('name','')) or w in str(u.get('sku','')) for w in ALIASES[key]):continue
  try:
   e=float(u.get('expires_at')) if u.get('expires_at') is not None else None
   if e is not None and e<=now:continue
   if avoid and e is not None and e-now<86400:continue
  except:e=None
  g=str(u.get('grade') or '').upper()
  if exclude_c and g=='C':continue
  if minimum and RANK.get(g,-1)<RANK[minimum]:continue
  cand.append(u)
 if not cand:return {'reply':'요청하신 조건에 맞는 '+key+' 재고가 지금 없어요. 다른 물건으로 대신 권하지 않겠습니다.','state':'completed'}
 def ex(u):
  try:return float(u.get('expires_at')) if u.get('expires_at') is not None else float('inf')
  except:return float('inf')
 u=max(cand,key=ex) if avoid else min(cand,key=ex);g=str(u.get('grade') or '미상');e=u.get('expires_at')
 if e is None:et='소비기한 없음'
 else:
  try:left=max(0,int(float(e)-now));et=f'소비기한까지 약 {left//3600}시간 {(left%3600)//60}분 남았어요'
  except:et='소비기한을 확인할 수 없어요'
 cost=int(u.get('cost') or 0);p=((cost+210)*100+98)//99;base=f'{u.get("name",key)} 재고가 있어요. 실측 {g}급, {et}, {p}크레딧입니다.'
 if not any(x in text for x in ['결제','구매','사고','살게','주세요','부탁','checkout']):return {'reply':base+' 구매하시면 결제서를 바로 보내드릴게요.','state':'completed'}
 try:
  from importlib.util import spec_from_file_location,module_from_spec
  s=spec_from_file_location('mc','tools/make_checkout/logic.py');m=module_from_spec(s);s.loader.exec_module(m);res=m.run({'sku':u['sku'],'unit':u['unit'],'price':p,'cost':cost,'task':args.get('task_id')},kit)
 except Exception:res={}
 return {'reply':base+(' 결제서를 지금 보냅니다.' if res.get('checkout_jwt') else ' 다만 지금 결제서 발급에 실패했어요.'),'data':res if res.get('checkout_jwt') else None,'state':'completed'}

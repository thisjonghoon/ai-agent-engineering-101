import time, httpx
ALIASES={'빵':['빵'],'우유':['우유'],'돼지고기':['돼지고기','돼지'],'소고기':['소고기','국거리'],'계란':['계란','달걀','유정란','특란'],'사과':['사과'],'시금치':['시금치'],'요거트':['요거트','요구르트'],'콩나물':['콩나물'],'취나물':['취나물'],'김치':['김치'],'티슈':['티슈','휴지','화장지','크리넥스'],'차':['차','둥굴레','둥굴레차']}
BLOCKED=['환불','불만','할인','흥정','여러','각각','또는','이나','말고','싫','안 삽니다','안사요','필요 없','보다 작','이하','이상','이내']
def run(args,kit):
 text=str(args.get('text') or '').strip()
 if not text or any(x in text for x in BLOCKED): return {'defer':True}
 keys=[k for k,v in ALIASES.items() if any(w in text for w in v)]
 if len(keys)!=1:return {'defer':True}
 try:
  if kit.testing: units=args.get('_units',[])
  else:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20);r.raise_for_status();units=r.json().get('units',[])
 except Exception:return {'reply':'재고를 확인하지 못했어요. 잠시 뒤 다시 문의해 주세요.','state':'completed'}
 cand=[u for u in units if any(w in str(u.get('name','')) for w in ALIASES[keys[0]]) and float(u.get('expires_at',0) or 0)>time.time()]
 if not cand:return {'reply':'말씀하신 품목은 지금 실제 재고가 없어요.','state':'completed'}
 cand.sort(key=lambda u:float(u.get('expires_at',0) or 0))
 for u in cand:
  grade=u.get('grade') or '미상';cert=u.get('cert') or {};inner=cert.get('cert',cert) if isinstance(cert,dict) else {};cert_grade=inner.get('grade') if isinstance(inner,dict) else None
  left=max(0,int(float(u.get('expires_at',0))-time.time()));h=left//3600;m=(left%3600)//60;price=((int(u.get('cost',0))+210)*100+98)//99
  base=f'{u.get("name")} 재고가 있어요. 실제 재고 등급은 {grade}이고 소비기한까지 약 {h}시간 {m}분 남았어요. 가격은 {price}크레딧입니다.'
  if cert_grade is not None and cert_grade!=grade:
   if len(cand)==1:return {'reply':base+f' 인증서 등급 {cert_grade}와 실측 등급이 달라 등급을 명시한 결제서는 발급할 수 없어요.','state':'completed'}
   continue
  if not any(x in text for x in ['checkout','결제','사고','구매','부탁']):return {'reply':base+(' 인증서의 grade는 비어 있어요.' if cert_grade is None else ' 인증서에도 같은 등급이 기재돼 있어요.'),'state':'completed'}
  try:
   from importlib.util import spec_from_file_location,module_from_spec
   s=spec_from_file_location('mc','tools/make_checkout/logic.py');mod=module_from_spec(s);s.loader.exec_module(mod)
   a={'sku':u['sku'],'unit':u['unit'],'price':price,'cost':int(u['cost']),'cert':u.get('cert'),'task':args.get('task_id')}
   if cert_grade is not None:a['claim']=grade
   res=mod.run(a,kit)
  except Exception: res={}
  if res.get('checkout_jwt'):return {'reply':base+(' 인증서 grade는 비어 있지만 실측 등급을 안내한 결제서를 보냅니다.' if cert_grade is None else ' 인증된 결제서를 보냅니다.'),'data':res,'state':'completed'}
 return {'reply':'현재 바로 발급할 수 있는 결제서가 없어 다른 재고도 확인했어요. 잠시 뒤 다시 문의해 주세요.','state':'completed'}
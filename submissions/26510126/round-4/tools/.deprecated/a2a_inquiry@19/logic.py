import httpx,time
ALIASES={'빵':['빵'],'우유':['우유'],'돼지고기':['돼지고기','돼지'],'소고기':['소고기','국거리'],'계란':['계란','달걀','유정란','특란'],'사과':['사과'],'시금치':['시금치'],'요거트':['요거트','요구르트'],'콩나물':['콩나물'],'취나물':['취나물'],'김치':['김치'],'티슈':['티슈','휴지','화장지','크리넥스']}
def run(args,kit):
 text=str(args.get('text') or '').strip()
 if not text:return {'defer':True}
 blocked=['환불','불만','할인','흥정','여러','각각','또는','이나','말고','싫','안 삽니다','안사요','필요 없','보다 작','이하','이상','이내']
 if any(x in text for x in blocked):return {'defer':True}
 keys=[k for k,v in ALIASES.items() if any(w in text for w in v)]
 if len(keys)!=1:return {'defer':True}
 try:
  if kit.testing: units=args.get('_units',[])
  else:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20);r.raise_for_status();units=r.json().get('units',[])
 except Exception:return {'reply':'재고를 확인하지 못했어요. 잠시 뒤 다시 문의해 주세요.','state':'completed'}
 cand=[u for u in units if any(w in str(u.get('name','')) for w in ALIASES[keys[0]]) and float(u.get('expires_at',0) or 0)>time.time()]
 if not cand:return {'reply':'말씀하신 품목은 지금 실제 재고가 없어요.','state':'completed'}
 cand.sort(key=lambda u:float(u.get('expires_at',0) or 0),reverse=True);u=cand[0]
 left=max(0,int(float(u.get('expires_at',0))-time.time()));h=left//3600;m=(left%3600)//60
 price=((int(u.get('cost',0))+210)*100+98)//99
 if not any(x in text for x in ['checkout','결제','사고','구매','부탁']):return {'reply':f"{u.get('name')} 재고가 있어요. {u.get('grade','미상')}등급, 소비기한까지 약 {h}시간 {m}분 남았고 가격은 {price}크레딧입니다.",'state':'completed'}
 try:
  from importlib.util import spec_from_file_location,module_from_spec
  s=spec_from_file_location('mc','tools/make_checkout/logic.py');mod=module_from_spec(s);s.loader.exec_module(mod)
  res=mod.run({'sku':u['sku'],'unit':u['unit'],'price':price,'cost':int(u['cost']),'cert':u.get('cert'),'claim':u.get('grade'),'task':args.get('task_id')},kit)
 except Exception:
  return {'reply':'결제서를 발급하지 못했어요. 재고를 다시 확인해 주세요.','state':'completed'}
 if res.get('checkout_jwt'):
  return {'reply':f"{u.get('name')} {u.get('grade','미상')}등급, 소비기한까지 약 {h}시간 {m}분 남았어요. 가격은 {price}크레딧입니다. 서명된 결제서를 보냅니다.",'data':res,'state':'completed'}
 return {'reply':'지금은 해당 상품의 결제서를 발급할 수 없어요.','state':'completed'}

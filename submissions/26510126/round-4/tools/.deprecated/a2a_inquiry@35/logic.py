import time,httpx
GROUPS={'과일':['사과','배','감','귤','바나나','포도'],'채소':['시금치','콩나물','취나물'],'유제품':['우유','요거트']}
def run(args,kit):
 text=str(args.get('text') or '').strip()
 try:
  if kit.testing: units=args.get('_units',[])
  else:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20);r.raise_for_status();units=r.json().get('units',[])
 except Exception:return {'reply':'재고를 확인하지 못했어요. 잠시 뒤 다시 문의해 주세요.','state':'completed'}
 def vals(u): return [str(u.get(k) or '') for k in ('name','sku','category','catalog_category','product_category','classification','catalog')]
 def fields(u): return ' '.join(vals(u))
 selected=[u for u in units if any(v and v in text for v in vals(u))]
 if not selected:
  terms=next((v for g,v in GROUPS.items() if g in text),[]);selected=[u for u in units if any(t in fields(u) for t in terms)]
 if len(selected)>1:return {'reply':'여러 품목이 맞을 수 있어 상품명을 한 가지로 말씀해 주세요.','state':'completed'}
 if not selected:return {'reply':'말씀하신 품목은 지금 실제 재고가 없어요.','state':'completed'}
 now=0 if kit.testing else time.time();valid=[]
 for u in selected:
  try:e=float(u.get('expires_at')) if u.get('expires_at') is not None else None
  except:e=None
  if e is None or e>now:valid.append(u)
 if not valid:return {'reply':'조건에 맞는 말씀하신 품목은 지금 실제 재고가 없어요.','state':'completed'}
 u=min(valid,key=lambda x:float(x.get('expires_at') or 1e99));e=u.get('expires_at');g=str(u.get('grade') or '미상');left=0 if e is None else max(0,int(float(e)-now));et='소비기한 없음' if e is None else '소비기한까지 약 %d시간 %d분 남았어요.'%(left//3600,(left%3600)//60);cost=int(u.get('cost') or 0);price=((cost+210)*100+98)//99
 return {'reply':f'{u.get("name",u.get("sku"))} 재고가 있어요. 분류/검색어는 {text}, 실제 정보는 {fields(u)}입니다. 실측 {g}급, {et} 가격은 {price}크레딧입니다. 구매하시면 결제서를 바로 보내드릴게요.','state':'completed'}
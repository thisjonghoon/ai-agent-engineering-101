import httpx,json

def run(args,kit):
 text=str(args.get('text','')).strip()
 if not text:
  try:
   with open('card.json',encoding='utf-8') as f: c=json.load(f)
   text='thisjonghoon 가게 안내: 현재 공개 재고를 판매합니다. 품목별 등급·인증서 등급·잔여시간은 문의 시 측정해 정확히 안내하고, 아직 확인하지 못한 사항은 숨기지 않겠습니다.'
  except Exception:
   text='thisjonghoon 가게 안내: 재고와 상태를 정직하게 안내합니다. 확인하지 못한 사항은 확인하지 못했다고 말씀드리겠습니다.'
 if len(text)>2000: text=text[:2000]
 r=httpx.post(kit.market+'/api/forum',headers={'authorization':'Bearer '+kit.token('shop')},json={'text':text,'refs':[]},timeout=15)
 return {'status':r.status_code,'result':r.json()}

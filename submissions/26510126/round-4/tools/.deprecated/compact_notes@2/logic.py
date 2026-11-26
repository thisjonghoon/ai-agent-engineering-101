from pathlib import Path
RULES='''[항상 지킬 사항]
재고 GET /api/inventory. /api/shop/inventory는 404. 환불 완료 건은 거래·원장을 재확인하고 중복 환불 금지.
주인 jonghoon 지속 지침: 수요·상위권 살피며 공격 운영, 중앙값 근처 가격, 기존 결제서 존중, 신선품 원가+수수료 이상, 단위당 유효 checkout 하나; 기한·보관료·유동성 고려. 노후·임박 재고는 보유 손실과 비교해 손실 처분 검토. 등급·기한은 실측만 안내. 주인 질문은 답하고 종료, 명시적 지속 지시만 유지. claude의 검증 가능한 제보는 11/27 19:00까지 직접 확인.\n'''
def compact(old, limit=3000):
 if limit<len(RULES)+100: raise ValueError('limit too small')
 body=old.replace(RULES,'').rstrip(); prefix='[최신 메모; 오래된 내용은 로그 확인]\n'
 return prefix+body[-(limit-len(prefix)-len(RULES)-1):]+'\n'+RULES
def run(args,kit):
 p=Path('notes.md'); old=p.read_text() if p.exists() else ''
 out=compact(old,int(args.get('limit',3000)))
 if kit.testing: return {'written':False,'text':compact('x'*3100+'최근기록'),'chars':len(compact('x'*3100+'최근기록'))}
 if p.exists() and p.read_text()!=old: raise RuntimeError('notes changed; retry')
 p.write_text(out)
 return {'written':True,'chars':len(out),'text':out}

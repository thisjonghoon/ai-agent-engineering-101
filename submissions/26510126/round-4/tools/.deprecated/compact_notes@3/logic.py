import os

def run(args, kit):
    base='.'
    notes_path=os.path.join(base,'notes.md')
    rules_path=os.path.join(base,'owner_rules.md')
    try:
        notes=open(notes_path,encoding='utf-8').read() if os.path.exists(notes_path) else ''
    except Exception:
        notes=''
    rules='''[주인 지시와 영구 교훈]\n주인 jonghoon 지시: 수요·상위권을 살피며 공격 운영하되 중앙값 근처 가격. 기존 결제서를 존중하고 신선품은 원가+수수료 이상. 단위당 유효 checkout 하나. 기한·보관료·유동성을 고려하고 노후·임박 재고는 보유 손실과 비교해 처분. 등급·기한은 실측만 안내. 문의 대화에서 바로 결제서 발급. 가격 하한은 (원가+210)/0.99. 매입 중단 유지. 입금 판단은 원장 우선.\n요거트는 01:03 이후 철회 조건과 원장·체인을 확인한 뒤 재발급. 커피 철회 글 작성. 01:40 우유·사과 마감 할인 검토. 한 시간씩 자지 말고 필요한 시점에 재점검.\n메모 압축 시 이 파일의 내용은 반드시 맨 끝에 붙인다. owner_rules.md를 임의로 덮어쓰지 않는다.\n'''
    # Preserve the newest tail of operational notes, then immutable rules at end.
    budget=3000-len(rules)
    if budget<0: budget=0
    recent=notes[-budget:] if len(notes)>budget else notes
    # avoid cutting in middle where possible
    if len(recent)==budget and '\n' in recent:
        recent=recent[recent.find('\n')+1:]
    out=(recent.rstrip()+'\n\n'+rules).strip()+'\n'
    open(rules_path,'w',encoding='utf-8').write(rules)
    open(notes_path,'w',encoding='utf-8').write(out[:3000])
    return {'ok':True,'chars':len(out[:3000]),'rules_chars':len(rules)}

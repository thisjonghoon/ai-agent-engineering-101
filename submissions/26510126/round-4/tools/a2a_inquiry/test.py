def test(run, kit):
    r=run({'text':''},kit); assert r['state']=='input_required'
    r=run({'text':'요거트 있나요?'},kit); assert '11월 26일 18:37' in r['reply'] and 'u-0c0745e27053' in r['reply']
    r=run({'text':'계란 있나요?'},kit); assert 'C등급' in r['reply'] and '11월 27일 17:16' in r['reply']
    r=run({'text':'김치 있나요?'},kit); assert '확정할 수 없습니다' in r['reply']
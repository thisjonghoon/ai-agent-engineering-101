def test(run, kit):
    import json
    with open('card.json','w') as f: json.dump({'stock':[{'id':'a','item':'사과','grade':'A','quantity':1,'price':1200,'time_left':'2일','certificate_grade':None}]},f)
    r=run({'text':'사과 재고 있나요?','claimed_from':'x'},kit)
    assert '사과' in r['reply']
    r=run({'text':'사과 구매하고 싶어요','claimed_from':'x'},kit)
    assert r['state']=='completed' and '1200' in r['reply']

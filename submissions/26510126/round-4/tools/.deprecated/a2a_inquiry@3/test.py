def test(run, kit):
    r = run({'text':''}, kit)
    assert r['state'] == 'input_required'
    r = run({'text':'사과 있나요?'}, kit)
    assert '지나' in r['reply']
    r = run({'text':'요거트 있나요?'}, kit)
    assert 'u-0c0745e27053' in r['reply']
    r = run({'text':'우유 있나요?'}, kit)
    assert '요거트' in r['reply']

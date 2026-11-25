def test(run, kit):
    r = run({'text':''}, kit)
    assert r['state'] == 'input_required'
    r = run({'text':'계란 있나요?'}, kit)
    assert r['state'] == 'completed'
    assert 'B등급' in r['reply']
    r = run({'text':'우유 있나요?'}, kit)
    assert r['state'] == 'completed'
    assert '사과' in r['reply']

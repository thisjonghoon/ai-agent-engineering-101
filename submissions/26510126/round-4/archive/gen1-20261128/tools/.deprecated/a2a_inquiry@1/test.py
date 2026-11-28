def test(run, kit):
    r = run({'text': ''}, kit)
    assert r['state'] == 'input_required'
    r = run({'text': '계란 있나요?'}, kit)
    assert r.get('defer') is True

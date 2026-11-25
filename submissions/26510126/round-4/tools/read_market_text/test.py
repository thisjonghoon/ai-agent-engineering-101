def test(run, kit):
    r=run({'url':'https://market.ourolabs.ai/ROUND4.md','max_chars':1000},kit)
    assert r['status']==200
    assert isinstance(r['text'],str)

def test(run, kit):
    out = run({'url': 'https://elsewhere.invalid/x'}, kit)
    assert 'error' in out
    out2 = run({'url': kit.market + '/ROUND4.md', 'max': 100}, kit)
    assert 'status' in out2 or 'error' in out2

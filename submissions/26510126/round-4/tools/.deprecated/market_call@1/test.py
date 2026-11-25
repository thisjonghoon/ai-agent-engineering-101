def test(run, kit):
    out = run({'method': 'GET', 'path': 'http://evil/x'}, kit)
    assert 'error' in out

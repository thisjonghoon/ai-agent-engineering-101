def test(run, kit):
    out = run({'address': 'nope'}, kit)
    assert 'error' in out

def test(run, kit):
    assert 'error' in run({'path':'http://evil/x'},kit)

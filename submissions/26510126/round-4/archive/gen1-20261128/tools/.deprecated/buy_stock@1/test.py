def test(run, kit):
    out = run({'sku': 'x'}, kit)
    assert 'error' in out

def test(run, kit):
    assert kit.testing
    out=run({'max':10},kit)
    assert isinstance(out,dict)
    assert 'by_sku' in out
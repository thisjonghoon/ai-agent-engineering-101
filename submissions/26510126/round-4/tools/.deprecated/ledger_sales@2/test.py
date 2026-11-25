def test(run,kit):
    assert kit.testing
    out=run({'max':10},kit)
    assert isinstance(out,dict) and 'by_sku' in out and 'sales' in out
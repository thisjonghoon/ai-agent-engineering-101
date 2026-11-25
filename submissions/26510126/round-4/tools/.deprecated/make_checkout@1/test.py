def test(run, kit):
    bad = run({'sku': 's', 'unit': 'u', 'price': 1000, 'cost': 5000}, kit)
    assert 'error' in bad
    ok = run({'sku': 's', 'unit': 'u', 'price': 10000, 'cost': 5000, 'claim': 'A'}, kit)
    assert 'checkout_jwt' in ok
    assert ok['shop_gets'] == 10000 - 100 - 210

def test(run, kit):
    r=run({'to':'0x0000000000000000000000000000000000000001','credits':1}, kit)
    assert r['tx_hash'].startswith('0x')

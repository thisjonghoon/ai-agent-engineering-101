def test(run, kit):
    if kit.testing:
        return
    x=run({'tx_hash':'0x9e4cf3469d4e83f006b81cbc37b53736b194ac1fe25dbf0bda7c0610f8f4b2d1'},kit)
    assert isinstance(x,dict)

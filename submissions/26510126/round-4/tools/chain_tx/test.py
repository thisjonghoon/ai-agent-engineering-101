def test(run, kit):
    out=run({'tx_hash':'0x'+'0'*64},kit)
    assert out['rpc']['jsonrpc']=='2.0'

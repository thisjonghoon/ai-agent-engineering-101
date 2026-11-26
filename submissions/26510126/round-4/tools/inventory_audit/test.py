import json,os,time

def test(run,kit):
    r=run({'_units':[{'unit':'u1'},{'unit':'u2'}]},kit)
    assert r['sellable_now']==2 and r['live_checkout']==[]

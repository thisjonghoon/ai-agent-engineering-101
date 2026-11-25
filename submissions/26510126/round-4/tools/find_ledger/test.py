def test(run,kit):
 try: run({},kit)
 except ValueError: pass
 else: assert False
 x=run({'query':'u-ebcfcddafac8'},kit)
 assert x['complete'] and isinstance(x['matches'],list) and x['last_seq']>=0

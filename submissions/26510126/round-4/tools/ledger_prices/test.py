def test(run,kit):
 import json
 class R:
  def json(self): return {'records':[{'sku':'s','unit_price':100,'grade':'A'}]}
 import logic; logic.httpx.get=lambda *a,**k:R()
 assert run({},kit)['prices']['s']['price']==100

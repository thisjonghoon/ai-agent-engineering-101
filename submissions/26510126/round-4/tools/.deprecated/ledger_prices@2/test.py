def test(run,kit):
 import json
 class R:
  def json(self): return [{'sku':'s1','grade':'A','price':100},{'sku':'s1','grade':'A','price':120},{'sku':'s2','grade':'B','price':80}]
 import logic
 logic.httpx.get=lambda *a,**k:R()
 out=run({},kit); assert out['priced']==2
 with open('prices.json') as f: assert json.load(f)['s1']['price']==110

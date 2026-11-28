def test(run,kit):
 u=[{'name':'계란','sku':'e','unit':'c','expires_at':9999999999,'grade':'C','cost':100},{'name':'계란','sku':'e','unit':'b','expires_at':9999999999,'grade':'B','cost':100}]
 r=run({'text':'계란 C급 제외 있나요?','_units':u},kit)
 assert '실제 재고 등급은 B' in r['reply']
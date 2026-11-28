def test(run,kit):
 u=[{'name':'계란','sku':'e','unit':'c','expires_at':9999999999,'grade':'C','cost':100},{'name':'계란','sku':'e','unit':'b','expires_at':9999999999,'grade':'B','cost':100}]
 assert '실측 B급' in run({'text':'계란 C급 제외 있나요?','_units':u},kit)['reply']
 c=[{'name':'치킨','sku':'c','unit':'1','expires_at':9999999999,'grade':'B','cost':100}]
 assert '여러 품목' not in run({'text':'바삭한 치킨, 냉동 너겟 말고 치킨 있어요?','_units':c},kit)['reply']
 assert '여러 품목' in run({'text':'계란과 두부 주세요','_units':u},kit)['reply']
 t=[{'name':'크리넥스','sku':'t','unit':'1','expires_at':9999999999,'grade':'A','cost':100}]
 assert '크리넥스 재고' in run({'text':'크리넥스 구매할게요','_units':t},kit)['reply']
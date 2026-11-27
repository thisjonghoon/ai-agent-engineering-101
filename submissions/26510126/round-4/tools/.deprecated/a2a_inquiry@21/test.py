def test(run,kit):
 u={'unit':'u1','sku':'Gx','name':'김치','grade':'C','cert':{'cert':{'grade':None}},'cost':700,'expires_at':9999999999}
 r=run({'text':'김치 구매하고 싶어요','_units':[u]},kit)
 assert r.get('state')=='completed' and '인증서' in r.get('reply','')
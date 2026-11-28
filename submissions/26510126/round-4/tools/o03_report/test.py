import json,os
def test(run,kit):
 json.dump({'stock':{'S':1}},open('card.json','w')); json.dump([{'sku':'S','name':'테스트','grade':'A','unit':'개','cost':100}],open('catalog.json','w'))
 os.makedirs('logs',exist_ok=True); open('logs/talk.jsonl','w').write(json.dumps({'ts':1795867201,'text':'테스트 구매'})+'\n')
 r=run({},kit); assert r['sku_count']==1 and r['message_count']==1 and r['sku_rows'][0]['floor']>=313
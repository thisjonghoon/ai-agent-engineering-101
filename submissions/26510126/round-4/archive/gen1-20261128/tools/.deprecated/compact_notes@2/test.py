def test(run,kit):
 r=run({},kit)
 assert not r['written'] and r['chars']<=3000 and '최근기록' in r['text'] and '/api/inventory' in r['text'] and '주인 jonghoon' in r['text']

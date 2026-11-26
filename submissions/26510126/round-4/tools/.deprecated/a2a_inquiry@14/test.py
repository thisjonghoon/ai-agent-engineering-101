import time


def test(run, kit):
    now = int(time.time())
    units = [
        {'unit':'a', 'sku':'G02595b69', 'name':'계란 40구', 'grade':'A', 'expires_at':now + 180000},
        {'unit':'b', 'sku':'G02595b69', 'name':'계란 40구', 'grade':'B', 'expires_at':now + 120000},
        {'unit':'c', 'sku':'G02595b69', 'name':'계란 40구', 'grade':'C', 'expires_at':now + 200000},
        {'unit':'short', 'sku':'G02595b69', 'name':'계란 40구', 'grade':'B', 'expires_at':now + 600},
        {'unit':'unknown', 'sku':'G02595b69', 'name':'계란 40구', 'grade':'A'},
        {'unit':'small', 'sku':'Gab7c8b3d', 'name':'계란 20구', 'grade':'A', 'expires_at':now + 210000},
    ]
    def ask(text):
        return run({'text':text, '_units':units, '_inspect_candidates':True}, kit)
    assert ask('G02595b69 계란 40구 B등급 이상, 소비기한 24시간 이상') == {'units':['a','b']}
    assert ask('G02595b69 계란 40구 B등급 이하') == {'units':['c','b','short']}
    assert ask('G02595b69 계란 40구 B등급') == {'units':['b','short']}
    assert ask('G02595b69 계란 20구 대체 없음') == {'units':[]}
    assert ask('계란 20구 A등급') == {'units':['small']}
    assert ask('계란 C등급이거나 소비기한이 짧은 건 안 사겠다') == {'defer':True}
    assert ask('계란 소비기한 넉넉한 걸로') == {'defer':True}
    assert ask('계란 B등급 이상, 소비기한 내일까지') == {'defer':True}
    assert ask('계란 40구 1+등급') == {'defer':True}
    assert ask('환불해주세요') == {'defer':True}
    assert '없' in run({'text':'우유 있나요?', '_units':[]}, kit)['reply']

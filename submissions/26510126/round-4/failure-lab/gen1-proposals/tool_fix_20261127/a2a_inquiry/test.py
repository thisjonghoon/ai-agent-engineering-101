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
    assert ask('계란 소비기한 넉넉한 걸로') == {'units':['small','c','a','b','short','unknown']}
    assert ask('G02595b69 계란 40구 현재 등급과 소비기한까지 남은 시간 알려주세요') == {'units':['c','a','b','short','unknown']}
    assert ask('계란 소비기한 짧은 건 빼주세요') == {'defer':True}
    assert ask('계란은 C등급이나 기한이 몇 시간뿐인 건 피하고 싶어요') == {'defer':True}
    assert ask('계란 3일 남은 걸로') == {'defer':True}
    assert ask('계란 특등급 있나요') == {'defer':True}
    assert ask('나물 반찬이나 비빔밥용 신선 채소 찾습니다') == {'defer':True}
    yog = [{'unit':'y', 'sku':'G5e1cf31d', 'name':'후디스 그릭요거트 플레인 400g 2개입', 'grade':'A', 'expires_at':now + 90000}]
    assert run({'text':'후디스 그릭요거트 450g A등급 있나요? 소비기한과 가격', '_units':yog, '_inspect_candidates':True}, kit) == {'units':[]}
    assert run({'text':'후디스 그릭요거트 450g A등급 있나요? 소비기한과 가격', '_units':yog}, kit) == {'defer':True}
    assert run({'text':'후디스 그릭요거트 400g A등급 있나요? 소비기한과 가격', '_units':yog, '_inspect_candidates':True}, kit) == {'units':['y']}
    assert ask('계란 B등급 이상, 소비기한 내일까지') == {'defer':True}
    assert ask('계란 40구 1+등급') == {'defer':True}
    assert ask('환불해주세요') == {'defer':True}
    assert '없' in run({'text':'우유 있나요?', '_units':[]}, kit)['reply']

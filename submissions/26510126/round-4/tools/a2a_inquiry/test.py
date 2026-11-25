def test(run,kit):
    assert run({'text':''},kit)['state']=='input_required'
    assert run({'text':'사과 구매할게요'},kit)=={'defer':True}
    assert run({'text':'안녕하세요'},kit)=={'defer':True}

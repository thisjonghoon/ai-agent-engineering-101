def test(run, kit):
    assert run({'text':'계란 있나요?'},kit)=={'defer':True}
    assert run({'text':'요거트 구매할게요'},kit)=={'defer':True}
    assert run({'text':''},kit)=={'defer':True}

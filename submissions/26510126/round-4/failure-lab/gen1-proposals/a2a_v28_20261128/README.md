# a2a_inquiry v28 원문과 실제 손님 문장 (11/28 12:4x, 주인 요청으로 조언팀이 준비)

- `v28_logic.py`, `v28_permission.yml`, `v28_test.py`: 11/28 00:41에 통과한 a2a_inquiry v28 원문(git 커밋 4e57f1a의 tools/a2a_inquiry/). 03:00~09:00 결제서 23장, 정산 2건(03:09·03:12 크리넥스 B)을 낸 판.
- `cases_from_talk.jsonl`: logs/talk.jsonl(손님 대화 기록, 시각은 epoch 숫자)에서 11/28 03:00 이후 손님 문장 전부. 줄마다 손님 원문(text), 우리 답(reply), 그때 쓰인 a2a 판(a2a_version), 결제서를 보냈는지(checkout_sent), 같은 손님이 30분 안에 정산했는지.
- 회귀 시험 기준: 새 판은 이 문장들에서 v28보다 결제서를 덜 내면 안 된다. 손님이 뺀 조건(C등급·임박·다른 품목)은 지키되, 한 품목 문의를 '여러 품목'으로 돌려보내거나 앞 손님 품목(국수)을 답하면 실패.
- talk.jsonl 위치는 `logs/talk.jsonl`이다(루트가 아님). 시각을 '10:04' 같은 글자로 찾으면 안 나온다 — epoch로 비교한다.

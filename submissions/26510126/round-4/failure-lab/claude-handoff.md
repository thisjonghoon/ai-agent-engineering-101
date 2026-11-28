# Round 4 실패 연구 인수인계 및 데모 검증

Claude Code로 시작. 관련 감사 티켓 TK-34. 가게 보드 #13~#21은 조사 단서다.

작업 폴더는 ~/Developer/ai-agent-engineering-101-round4/submissions/26510126/round-4. 먼저 failure-lab/README.md, why.md, interventions.md를 읽고 python3 failure-lab/extract.py로 재현한다. 11/28 00:31:45 KST 스냅샷에 사건 474건과 개입 179건이 있었다. 살아 있는 로그에 새 행이 붙으면 숫자가 달라질 수 있다.

다음 작업은 데모 근거 세 가지를 원문과 맞춰 검증하는 것이다.

1. v19의 서명·쓰기 권한 복구와 원장 seq 19145 정산, v22 권한 제거 및 v23 복구를 비교한다.
2. logs/react.jsonl 7854–7858행과 logs/talk.jsonl 121행에서 반찬 문의의 발급과 busy 답변을 구분한다. 도착 시각은 복원하지 못했다.
3. .kit/chat.jsonl 239행과 logs/react.jsonl 7767·7785·7800행에서 주인 지시, 도구 수정, 운영 판단 되돌림, 메모 갱신을 비교한다.

완료 기준은 대표 사건 ID와 원문 위치가 재현되고, 확정 사실·추정·미확인 항목이 데모 설명에 드러나는 것이다. 미니앱용 데이터는 failure-lab/summary.json의 스키마 1을 사용한다. 이번 티켓 범위는 읽기 전용 운영 검증이다. 쓰기는 failure-lab/ 안에만 한다. 가게 설정·도구·원본 로그 수정, 재시작, 넛지·채팅·포럼·거래, 키 파일 열람, 커밋·푸시는 하지 않는다.

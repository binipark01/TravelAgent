# AGENTS.md

설명할 때 필수적인 용어 제외하고 한글로 작성하기.

이 저장소는 CRUD 앱이 아니라 agent-runtime 프로젝트입니다.

규칙:

- agents는 tool을 호출한다.
- tools는 connector를 호출한다.
- connectors는 provider/source output을 evidence로 normalize한다.
- final plan에는 raw provider data를 직접 넣지 않는다.
- mock data는 dev/test/fallback으로만 사용하고 live처럼 표시하지 않는다.
- 실제 결제, 발권, 예약, 취소, 이메일, calendar side effect 금지.
- booking simulation은 approval gate 뒤에서만 실행한다.
- tests는 live network를 호출하지 않는다.

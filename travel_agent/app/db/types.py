"""DB 컬럼용 datetime 정규화 타입(항상 tz-aware UTC).

문제: 컬럼을 DateTime(timezone=True)로 선언해도 SQLite는 tz를 무시하고 naive로 저장·반환한다.
그런데 코드(utc_now)는 aware UTC를 만든다 → DB에서 돌아온 naive 값과 in-memory aware 값을 빼면
TypeError("can't subtract offset-naive and offset-aware datetimes")가 난다(특히 step latency:
started_at은 DB에서 naive로, completed_at은 방금 대입한 aware로 와서 혼재).

해결(근본): 모든 datetime 컬럼을 이 타입으로 통일해 backend와 무관하게 항상 aware-UTC로 다룬다.
- bind(저장): naive면 UTC로 간주해 tz를 붙인 뒤 저장(SQLite는 어차피 naive 문자열로 보관).
- result(조회): 값을 항상 aware-UTC로 만들어 돌려준다(naive면 UTC tz 부여).
이로써 DB에서 온 값·utc_now()로 만든 값·Pydantic을 거친 값이 전부 aware-UTC라 혼재가 사라진다.

직렬화 영향: started_at/completed_at/created_at 등 ISO 문자열이 offset 없음(...) →
'+00:00'(UTC) 표기로 바뀐다. 프론트 타입은 이 필드를 불투명 string으로 다루고(파싱 무관),
테스트 픽스처도 이미 'Z' 표기를 쓰므로 안전하다. UTC 절대시각 자체는 동일하다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """저장·조회 시 datetime을 tz-aware UTC로 통일하는 컬럼 타입(naive/aware 혼재 방지)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

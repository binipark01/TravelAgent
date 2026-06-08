from __future__ import annotations

from datetime import datetime

from travel_agent.app.schemas.common import SourceRef
from travel_agent.app.schemas.providers import ProviderMetadata
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now


def mock_metadata(provider_name: str, title: str, reference_prefix: str) -> ProviderMetadata:
    now = utc_now()
    expires_at = expires_in(12)
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider=provider_name,
        title=title,
        reference=f"{reference_prefix}-{now.strftime('%Y%m%d%H%M%S')}",
        retrieved_at=now,
        expires_at=expires_at,
        is_mock=True,
        freshness_note="Simulated mock data; verify price, availability, and rules before booking.",
    )
    return ProviderMetadata(
        provider_name=provider_name,
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_at,
        normalized_currency=None,
        is_mock=True,
    )


def combine_date_time(date_value, hour: int, minute: int = 0) -> datetime:
    return datetime(
        date_value.year,
        date_value.month,
        date_value.day,
        hour,
        minute,
        tzinfo=utc_now().tzinfo,
    )

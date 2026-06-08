from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import Field

from travel_agent.app.config import Settings
from travel_agent.app.connectors.accommodations import build_accommodation_connector
from travel_agent.app.connectors.base import ConnectorResult
from travel_agent.app.connectors.errors import ProviderConfigurationError
from travel_agent.app.evidence.models import EvidenceSourceRef
from travel_agent.app.schemas.common import Location, Money, SourceRef, StrictBaseModel
from travel_agent.app.schemas.providers import (
    AccommodationOption,
    AccommodationSearchRequest,
    ProviderMetadata,
)
from travel_agent.app.sources.registry import SourceRegistry
from travel_agent.app.utils.ids import new_id


class NormalizedAccommodationItem(StrictBaseModel):
    name: str
    area: str | None = None
    country: str | None = None
    nightly_amount: float
    total_amount: float
    currency: str
    rating: float | None = None
    cancellation_policy: str
    notes: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class AccommodationSearchTool:
    settings: Settings
    registry: SourceRegistry = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry", SourceRegistry(self.settings))

    def search(self, request: AccommodationSearchRequest) -> list[AccommodationOption]:
        options: list[AccommodationOption] = []
        for source in self.registry.get_enabled_sources("accommodations"):
            connector = build_accommodation_connector(source)
            if connector is None:
                continue
            try:
                result = connector.collect(request)
            except ProviderConfigurationError:
                if self.settings.provider_fallback_to_mock:
                    continue
                raise
            options.extend(self._options_from_result(request, result))
        return options

    def _options_from_result(
        self, request: AccommodationSearchRequest, result: ConnectorResult
    ) -> list[AccommodationOption]:
        return [
            self._option_from_item(
                request,
                NormalizedAccommodationItem.model_validate(item),
                result.source_ref,
            )
            for item in result.normalized_items
        ]

    def _option_from_item(
        self,
        request: AccommodationSearchRequest,
        item: NormalizedAccommodationItem,
        source_ref: EvidenceSourceRef,
    ) -> AccommodationOption:
        return AccommodationOption(
            option_id=new_id("acc"),
            name=item.name,
            location=Location(
                name=f"{request.destination} {item.area}" if item.area else request.destination,
                country=item.country,
                area=item.area,
            ),
            nightly_price=Money(amount=item.nightly_amount, currency=item.currency),
            total_price=Money(amount=item.total_amount, currency=item.currency),
            rating=item.rating,
            cancellation_policy=item.cancellation_policy,
            metadata=self._metadata_from_source_ref(source_ref),
            notes=item.notes,
        )

    def _metadata_from_source_ref(self, source_ref: EvidenceSourceRef) -> ProviderMetadata:
        return ProviderMetadata(
            provider_name=source_ref.provider,
            retrieved_at=source_ref.retrieved_at,
            source_ref=SourceRef(
                source_id=source_ref.source_id,
                provider=source_ref.provider,
                provider_ref=source_ref.provider_ref,
                source_url=source_ref.source_url,
                title=f"{source_ref.provider} accommodation search",
                reference=source_ref.provider_ref or source_ref.source_id,
                retrieved_at=source_ref.retrieved_at,
                expires_at=source_ref.expires_at,
                is_live=source_ref.is_live,
                is_mock=source_ref.is_mock,
                source_type=source_ref.source_type,
                confidence=source_ref.confidence,
                attribution=source_ref.attribution,
                license_notes=source_ref.license_notes,
                freshness_note=self._freshness_note(source_ref),
            ),
            expires_at=source_ref.expires_at,
            normalized_currency=None,
            is_mock=source_ref.is_mock,
        )

    def _freshness_note(self, source_ref: EvidenceSourceRef) -> str:
        if source_ref.is_mock:
            return "Simulated mock data; verify price, availability, and rules before booking."
        return "Provider-derived accommodation data must be repriced before booking."

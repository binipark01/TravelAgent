from __future__ import annotations

from travel_agent.app.schemas.approvals import ApprovalRequest, ApprovalStatus
from travel_agent.app.schemas.common import Money
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.hashing import payload_hash
from travel_agent.app.utils.time import ensure_utc, utc_now

SIDE_EFFECT_ACTIONS = {
    "booking",
    "flight_booking",
    "hotel_booking",
    "payment_request",
    "email_send",
    "calendar_event",
    "cancellation",
    "modification",
}

SENSITIVE_KEYS = {
    "passport_number",
    "birth_date",
    "legal_name",
    "phone",
    "email",
}


class GuardrailViolation(ValueError):
    pass


def approval_required_for_side_effects(action_type: str, approval: ApprovalRequest | None) -> None:
    if action_type in SIDE_EFFECT_ACTIONS and approval is None:
        raise GuardrailViolation("Side-effect action requires an explicit ApprovalRequest.")


def approval_must_belong_to_trip(trip_id: str, approval: ApprovalRequest) -> None:
    if approval.trip_id != trip_id:
        raise GuardrailViolation("Approval does not belong to this trip.")


def payload_hash_must_match_approval(payload: dict, approval: ApprovalRequest) -> None:
    actual = payload_hash(payload)
    if actual != approval.exact_payload_hash:
        raise GuardrailViolation("Payload hash does not match the approved request.")


def price_must_not_exceed_approval_ceiling(price: Money, approval: ApprovalRequest) -> None:
    if approval.price_ceiling is None:
        return
    if price.currency != approval.price_ceiling.currency:
        raise GuardrailViolation("Price currency differs from approval ceiling currency.")
    if price.amount > approval.price_ceiling.amount:
        raise GuardrailViolation("Price exceeds the approval ceiling.")


def approval_must_be_valid(approval: ApprovalRequest) -> None:
    if approval.status != ApprovalStatus.approved:
        raise GuardrailViolation("Approval is not approved.")
    if ensure_utc(approval.expires_at) <= utc_now():
        raise GuardrailViolation("Approval has expired.")


def cancellation_policy_must_be_acknowledged(value: bool) -> None:
    if not value:
        raise GuardrailViolation("Cancellation policy acknowledgement is required.")


def no_booking_if_missing_traveler_identity(state: TripPlanState, payload: dict) -> None:
    passport_country = (
        state.brief.passport_country if state.brief and state.brief.passport_country else None
    )
    if not passport_country and not payload.get("passport_country"):
        raise GuardrailViolation("Passport country is required before booking simulation.")
    if not payload.get("traveler_identity_confirmed"):
        raise GuardrailViolation(
            "Traveler identity confirmation is required before booking simulation."
        )


def no_sensitive_data_persistence_without_consent(payload: dict) -> None:
    if SENSITIVE_KEYS & payload.keys() and not payload.get("consent_to_store_sensitive_data"):
        raise GuardrailViolation("Sensitive traveler data requires explicit persistence consent.")

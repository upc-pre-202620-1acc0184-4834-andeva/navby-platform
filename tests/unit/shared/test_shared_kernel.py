from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest

from src.shared.application.application_error import ApplicationError
from src.shared.application.current_user import CurrentUser
from src.shared.application.result import Result
from src.shared.domain.aggregate_root import AggregateRoot
from src.shared.domain.domain_error import DomainError
from src.shared.domain.domain_event import DomainEvent
from src.shared.domain.integration_event import IntegrationEvent
from src.shared.infrastructure.in_memory_event_bus import InMemoryEventBus
from src.shared.interfaces.error_catalog import ERROR_CATALOG


@dataclass(frozen=True, slots=True)
class SampleIntegrationEvent(IntegrationEvent):
    event_type: ClassVar[str] = "sample.created"
    sample_id: UUID

    def to_payload(self) -> dict[str, Any]:
        return {"sample_id": str(self.sample_id)}


class DummyAggregate(AggregateRoot):
    def do_something(self, sample_id: UUID) -> None:
        self.record_event(
            SampleIntegrationEvent(
                event_id=uuid4(),
                occurred_at=datetime.now(UTC),
                sample_id=sample_id,
            )
        )


def test_aggregate_root_records_and_pulls_events() -> None:
    agg = DummyAggregate()
    sample_id = uuid4()
    agg.do_something(sample_id)

    events = agg.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], DomainEvent)
    assert isinstance(events[0], SampleIntegrationEvent)
    assert events[0].to_payload() == {"sample_id": str(sample_id)}
    assert agg.pull_events() == []


def test_domain_error_attributes() -> None:
    err = DomainError(code="INVALID_WEIGHTS", message="Weights must sum to 1")
    assert err.code == "INVALID_WEIGHTS"
    assert err.message == "Weights must sum to 1"


def test_result_success_and_failure() -> None:
    ok = Result.success(42)
    assert ok.is_success is True
    assert ok.value == 42
    with pytest.raises(ValueError):
        _ = ok.error

    err = ApplicationError(code="INSUFFICIENT_CREDITS", message="Not enough credits")
    fail: Result[int] = Result.failure(err)
    assert fail.is_success is False
    assert fail.error == err
    with pytest.raises(ValueError):
        _ = fail.value


def test_current_user_immutable() -> None:
    uid = uuid4()
    user = CurrentUser(user_id=uid, email="ana@mail.com", email_verified=True)
    assert user.user_id == uid
    assert user.email == "ana@mail.com"
    assert user.email_verified is True


def test_error_catalog_has_all_27_codes() -> None:
    expected_codes = {
        "VALIDATION_ERROR",
        "RATE_LIMITED",
        "UNAUTHENTICATED",
        "INTERNAL_ERROR",
        "EMAIL_ALREADY_REGISTERED",
        "TERMS_NOT_ACCEPTED",
        "DISPOSABLE_EMAIL",
        "INVALID_CREDENTIALS",
        "EMAIL_NOT_VERIFIED",
        "INVALID_OTP",
        "OTP_ATTEMPTS_EXCEEDED",
        "INVALID_RESET_TOKEN",
        "INVALID_REFRESH_TOKEN",
        "INVALID_GOOGLE_TOKEN",
        "AIRPORT_NOT_FOUND",
        "ROUTE_NOT_REACHABLE",
        "SEARCH_IN_PROGRESS",
        "INVALID_WEIGHTS",
        "INSUFFICIENT_CREDITS",
        "PROVIDER_UNAVAILABLE",
        "SEARCH_NOT_FOUND",
        "OFFER_NOT_FOUND",
        "ITINERARY_NOT_FOUND",
        "ITINERARY_LIMIT_REACHED",
        "PACKAGE_NOT_FOUND",
        "ORDER_NOT_FOUND",
        "INVALID_WEBHOOK_SIGNATURE",
    }
    assert set(ERROR_CATALOG.keys()) == expected_codes
    assert len(ERROR_CATALOG) == 27


async def test_in_memory_event_bus_publishes_to_subscribers() -> None:
    bus = InMemoryEventBus()
    received: list[IntegrationEvent] = []

    class Handler:
        async def handle(self, event: IntegrationEvent) -> None:
            received.append(event)

    bus.subscribe("sample.created", Handler())
    evt = SampleIntegrationEvent(
        event_id=uuid4(),
        occurred_at=datetime.now(UTC),
        sample_id=uuid4(),
    )
    await bus.publish(evt)
    assert received == [evt]

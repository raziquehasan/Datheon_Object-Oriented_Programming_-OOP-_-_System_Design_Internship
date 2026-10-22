"""
test_service.py — Unit tests for NotificationService dispatch orchestration and DI.
"""

from __future__ import annotations

import logging
import pytest

from notifications.exceptions import UnsupportedChannelError
from notifications.interfaces import NotificationSender
from notifications.models import DeliveryResult, Notification, NotificationPriority
from notifications.registry import SenderRegistry
from notifications.service import NotificationService


class MockSender(NotificationSender):
    """Configurable mock sender for testing service orchestration."""

    def __init__(self, name: str, should_succeed: bool = True, message: str = "ok") -> None:
        self._name = name
        self.should_succeed = should_succeed
        self.message = message
        self.received_notifications: list[Notification] = []

    @property
    def channel_name(self) -> str:
        return self._name

    def send(self, notification: Notification) -> DeliveryResult:
        self.received_notifications.append(notification)
        return DeliveryResult(
            notification_id=notification.notification_id,
            channel=self.channel_name,
            success=self.should_succeed,
            message=self.message,
            provider_ref=f"{self.channel_name}-ref" if self.should_succeed else None,
            error_details=None if self.should_succeed else "Forced mock failure",
        )


def test_service_initialization_with_injected_registry():
    registry = SenderRegistry()
    service = NotificationService(registry=registry)
    assert service.registry is registry


def test_service_rejects_invalid_registry():
    with pytest.raises(TypeError, match="Expected SenderRegistry"):
        NotificationService(registry=None)  # type: ignore[arg-type]


def test_service_send_single_channel_success():
    registry = SenderRegistry()
    email_mock = MockSender("email", should_succeed=True, message="Sent successfully")
    registry.register(email_mock)

    service = NotificationService(registry=registry)
    notif = Notification(recipient="alice@test.com", subject="Greeting", body="Hello")

    result = service.send(notif, "email")
    assert result.success is True
    assert result.channel == "email"
    assert result.message == "Sent successfully"
    assert len(email_mock.received_notifications) == 1


def test_service_send_unsupported_channel_raises():
    registry = SenderRegistry()
    service = NotificationService(registry=registry)
    notif = Notification(recipient="alice@test.com", subject="Greeting", body="Hello")

    with pytest.raises(UnsupportedChannelError, match="Channel 'carrier-pigeon' is not registered"):
        service.send(notif, "carrier-pigeon")


def test_service_dispatch_multiple_channels_all_succeed():
    registry = SenderRegistry()
    email_mock = MockSender("email", should_succeed=True)
    sms_mock = MockSender("sms", should_succeed=True)
    slack_mock = MockSender("slack", should_succeed=True)

    registry.register(email_mock)
    registry.register(sms_mock)
    registry.register(slack_mock)

    service = NotificationService(registry=registry)
    notif = Notification(recipient="target", subject="Urgent", body="All systems alert")

    results = service.dispatch(notif, ["email", "sms", "slack"])
    assert len(results) == 3
    assert [r.channel for r in results] == ["email", "sms", "slack"]
    assert all(r.success for r in results)


def test_service_dispatch_partial_success():
    """Verify that if one channel fails, others continue and report accurately."""
    registry = SenderRegistry()
    email_mock = MockSender("email", should_succeed=True, message="Email sent")
    sms_mock = MockSender("sms", should_succeed=False, message="SMS provider down")
    slack_mock = MockSender("slack", should_succeed=True, message="Slack sent")

    registry.register(email_mock)
    registry.register(sms_mock)
    registry.register(slack_mock)

    service = NotificationService(registry=registry)
    notif = Notification(recipient="target", subject="Alert", body="Content")

    results = service.dispatch(notif, ["email", "sms", "slack"])
    assert len(results) == 3

    email_res = next(r for r in results if r.channel == "email")
    sms_res = next(r for r in results if r.channel == "sms")
    slack_res = next(r for r in results if r.channel == "slack")

    assert email_res.success is True
    assert sms_res.success is False
    assert sms_res.error_details == "Forced mock failure"
    assert slack_res.success is True


def test_service_dispatch_all_channels_fail():
    """Verify that when all channels fail, all are reported as failed without crashing."""
    registry = SenderRegistry()
    registry.register(MockSender("email", should_succeed=False, message="Email fail"))
    registry.register(MockSender("sms", should_succeed=False, message="SMS fail"))

    service = NotificationService(registry=registry)
    notif = Notification(recipient="target", subject="Alert", body="Content")

    results = service.dispatch(notif, ["email", "sms"])
    assert len(results) == 2
    assert all(not r.success for r in results)


def test_service_dispatch_handles_unsupported_channel_gracefully():
    """Verify unsupported channels are recorded as failure DeliveryResults during multi-dispatch."""
    registry = SenderRegistry()
    registry.register(MockSender("email", should_succeed=True))

    service = NotificationService(registry=registry)
    notif = Notification(recipient="target", subject="Alert", body="Content")

    results = service.dispatch(notif, ["email", "unsupported-channel"])
    assert len(results) == 2

    assert results[0].channel == "email"
    assert results[0].success is True

    assert results[1].channel == "unsupported-channel"
    assert results[1].success is False
    assert "Unsupported channel" in results[1].message


def test_service_logging_without_secret_leakage(caplog):
    """Ensure logging captures dispatch events without leaking credentials or message bodies."""
    registry = SenderRegistry()
    registry.register(MockSender("email", should_succeed=True))

    service = NotificationService(registry=registry)
    secret_token = "SUPER_SECRET_TOKEN_DO_NOT_LOG"
    notif = Notification(
        recipient="user@example.com",
        subject="Secret alert",
        body=f"Confidential: {secret_token}",
    )

    with caplog.at_level(logging.INFO):
        service.send(notif, "email")

    captured = caplog.text
    assert secret_token not in captured
    assert "Dispatching notification" in captured
    assert notif.notification_id in captured

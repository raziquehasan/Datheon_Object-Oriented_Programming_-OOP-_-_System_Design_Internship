"""
test_registry.py — Unit tests for SenderRegistry mapping and lifecycle management.
"""

from __future__ import annotations

import pytest

from notifications.exceptions import UnsupportedChannelError
from notifications.interfaces import NotificationSender
from notifications.models import DeliveryResult, Notification
from notifications.registry import SenderRegistry


class StubSender(NotificationSender):
    """Minimal fake sender for registry testing."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def channel_name(self) -> str:
        return self._name

    def send(self, notification: Notification) -> DeliveryResult:
        return DeliveryResult(
            notification_id=notification.notification_id,
            channel=self.channel_name,
            success=True,
            message=f"{self.channel_name} delivered",
        )


def test_registry_registration_and_lookup():
    registry = SenderRegistry()
    email_sender = StubSender("email")
    sms_sender = StubSender("sms")

    registry.register(email_sender)
    registry.register(sms_sender)

    assert registry.get("email") is email_sender
    assert registry.get("sms") is sms_sender
    assert "email" in registry
    assert "sms" in registry
    assert "slack" not in registry
    assert len(registry) == 2


def test_registry_case_insensitive_lookup():
    registry = SenderRegistry()
    sender = StubSender("Email")
    registry.register(sender)

    assert registry.get("email") is sender
    assert registry.get("EMAIL") is sender
    assert registry.get("Email") is sender


def test_registry_unsupported_channel_raises():
    registry = SenderRegistry()
    with pytest.raises(UnsupportedChannelError, match="Channel 'discord' is not registered"):
        registry.get("discord")


def test_registry_duplicate_registration_rejected():
    registry = SenderRegistry()
    sender1 = StubSender("email")
    sender2 = StubSender("email")

    registry.register(sender1)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(sender2)

    # sender1 remains registered
    assert registry.get("email") is sender1


def test_registry_duplicate_registration_with_overwrite():
    registry = SenderRegistry()
    sender1 = StubSender("email")
    sender2 = StubSender("email")

    registry.register(sender1)
    registry.register(sender2, overwrite=True)

    # sender2 has replaced sender1
    assert registry.get("email") is sender2


def test_registry_unregister():
    registry = SenderRegistry()
    sender = StubSender("slack")
    registry.register(sender)

    assert "slack" in registry
    registry.unregister("slack")
    assert "slack" not in registry

    with pytest.raises(UnsupportedChannelError):
        registry.get("slack")


def test_registry_unregister_non_existent():
    registry = SenderRegistry()
    with pytest.raises(UnsupportedChannelError, match="not registered"):
        registry.unregister("non_existent")


def test_registry_registered_channels_sorted():
    registry = SenderRegistry()
    registry.register(StubSender("whatsapp"))
    registry.register(StubSender("email"))
    registry.register(StubSender("sms"))

    assert registry.registered_channels() == ["email", "sms", "whatsapp"]


def test_registry_rejects_non_sender():
    registry = SenderRegistry()
    with pytest.raises(TypeError, match="Expected instance of NotificationSender"):
        registry.register("not-a-sender")  # type: ignore[arg-type]


def test_registry_empty_or_invalid_channel_name():
    class BadSender(NotificationSender):
        @property
        def channel_name(self) -> str:
            return ""

        def send(self, notification: Notification) -> DeliveryResult:
            return DeliveryResult("id", "", True, "msg")

    registry = SenderRegistry()
    with pytest.raises(ValueError, match="non-empty string channel_name"):
        registry.register(BadSender())

    with pytest.raises(UnsupportedChannelError):
        registry.get("")

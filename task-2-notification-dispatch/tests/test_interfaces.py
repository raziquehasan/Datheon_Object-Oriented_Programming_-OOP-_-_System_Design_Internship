"""
test_interfaces.py — Verify abstract base class contracts for transports and senders.
"""

from __future__ import annotations

import pytest

from notifications.interfaces import NotificationSender, NotificationTransport
from notifications.models import DeliveryResult, Notification


def test_notification_transport_cannot_be_instantiated():
    """Verify NotificationTransport is an abstract class."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        NotificationTransport()  # type: ignore[abstract]


def test_notification_transport_incomplete_subclass():
    """Verify subclass without deliver method cannot be instantiated."""
    class IncompleteTransport(NotificationTransport):
        pass

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        IncompleteTransport()  # type: ignore[abstract]


def test_notification_transport_concrete_subclass():
    """Verify concrete subclass implementing deliver works as expected."""
    class FakeTransport(NotificationTransport):
        def deliver(self, formatted_payload: str, destination: str) -> tuple[bool, str, str | None]:
            return True, f"Mock delivered to {destination}", "fake-123"

    transport = FakeTransport()
    success, msg, ref = transport.deliver("payload", "dest")
    assert success is True
    assert "Mock delivered" in msg
    assert ref == "fake-123"


def test_notification_sender_cannot_be_instantiated():
    """Verify NotificationSender is an abstract class."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        NotificationSender()  # type: ignore[abstract]


def test_notification_sender_incomplete_subclass():
    """Verify subclass missing channel_name or send cannot be instantiated."""
    class MissingSend(NotificationSender):
        @property
        def channel_name(self) -> str:
            return "incomplete"

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        MissingSend()  # type: ignore[abstract]

    class MissingChannelName(NotificationSender):
        def send(self, notification: Notification) -> DeliveryResult:
            return DeliveryResult("id", "c", True, "ok")

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        MissingChannelName()  # type: ignore[abstract]


def test_notification_sender_concrete_subclass():
    """Verify concrete subclass implementing all required methods works."""
    class DummySender(NotificationSender):
        @property
        def channel_name(self) -> str:
            return "dummy"

        def send(self, notification: Notification) -> DeliveryResult:
            return DeliveryResult(
                notification_id=notification.notification_id,
                channel=self.channel_name,
                success=True,
                message="Dummy delivered",
                provider_ref="dummy-ref",
            )

    sender = DummySender()
    assert sender.channel_name == "dummy"
    notif = Notification(recipient="target", subject="Test", body="Body")
    result = sender.send(notif)
    assert result.success is True
    assert result.channel == "dummy"
    assert result.provider_ref == "dummy-ref"

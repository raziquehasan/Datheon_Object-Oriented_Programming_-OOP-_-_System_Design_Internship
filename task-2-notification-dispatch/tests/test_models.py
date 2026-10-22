"""
test_models.py — Unit tests for Notification, DeliveryResult, and NotificationPriority models.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
import uuid
import pytest

from notifications.exceptions import InvalidNotificationError
from notifications.models import DeliveryResult, Notification, NotificationPriority


def test_notification_creation_defaults():
    """Verify default values and auto-generation for Notification."""
    notif = Notification(
        recipient="user@example.com",
        subject="Alert Subject",
        body="This is an alert body.",
    )

    assert notif.recipient == "user@example.com"
    assert notif.subject == "Alert Subject"
    assert notif.body == "This is an alert body."
    assert notif.priority == NotificationPriority.NORMAL
    assert notif.metadata == {}
    assert isinstance(notif.created_at, datetime)

    # Check notification_id is a valid UUID4
    parsed_uuid = uuid.UUID(notif.notification_id)
    assert parsed_uuid.version == 4


def test_notification_custom_fields():
    """Verify custom fields (priority, metadata, custom ID) are preserved."""
    custom_id = "custom-id-999"
    notif = Notification(
        notification_id=custom_id,
        recipient="admin@company.com",
        subject="Database Failover",
        body="Replica promoted to primary.",
        priority=NotificationPriority.CRITICAL,
        metadata={"service": "postgres", "cluster": "us-east-1"},
    )

    assert notif.notification_id == custom_id
    assert notif.priority == NotificationPriority.CRITICAL
    assert notif.metadata["service"] == "postgres"
    assert notif.metadata["cluster"] == "us-east-1"


def test_notification_immutability():
    """Verify Notification is a frozen dataclass and cannot be modified."""
    notif = Notification(
        recipient="dev@datheon.io",
        subject="Hello",
        body="World",
    )

    with pytest.raises(FrozenInstanceError):
        notif.subject = "Modified"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        notif.recipient = "other@datheon.io"  # type: ignore[misc]


@pytest.mark.parametrize(
    "bad_recipient",
    ["", "   ", "\t\n", None, 12345, []],
)
def test_notification_invalid_recipient(bad_recipient):
    """Verify InvalidNotificationError is raised for non-string or whitespace recipient."""
    with pytest.raises(InvalidNotificationError, match="recipient must be a non-empty string"):
        Notification(
            recipient=bad_recipient,  # type: ignore[arg-type]
            subject="Valid Subject",
            body="Valid Body",
        )


@pytest.mark.parametrize(
    "bad_subject",
    ["", "   ", "\n", None, 999],
)
def test_notification_invalid_subject(bad_subject):
    """Verify InvalidNotificationError is raised for non-string or whitespace subject."""
    with pytest.raises(InvalidNotificationError, match="subject must be a non-empty string"):
        Notification(
            recipient="test@example.com",
            subject=bad_subject,  # type: ignore[arg-type]
            body="Valid Body",
        )


@pytest.mark.parametrize(
    "bad_body",
    ["", "   ", "\r\n", None, {}],
)
def test_notification_invalid_body(bad_body):
    """Verify InvalidNotificationError is raised for non-string or whitespace body."""
    with pytest.raises(InvalidNotificationError, match="body must be a non-empty string"):
        Notification(
            recipient="test@example.com",
            subject="Valid Subject",
            body=bad_body,  # type: ignore[arg-type]
        )


def test_notification_priority_values():
    """Verify all priorities are distinct and orderable."""
    assert NotificationPriority.LOW.value < NotificationPriority.NORMAL.value
    assert NotificationPriority.NORMAL.value < NotificationPriority.HIGH.value
    assert NotificationPriority.HIGH.value < NotificationPriority.CRITICAL.value


def test_delivery_result_success():
    """Verify DeliveryResult model creation on success."""
    result = DeliveryResult(
        notification_id="n-101",
        channel="email",
        success=True,
        message="Delivered successfully",
        provider_ref="provider-tx-456",
    )

    assert result.notification_id == "n-101"
    assert result.channel == "email"
    assert result.success is True
    assert result.message == "Delivered successfully"
    assert result.provider_ref == "provider-tx-456"
    assert result.error_details is None
    assert isinstance(result.timestamp, datetime)


def test_delivery_result_failure():
    """Verify DeliveryResult model creation on failure with error details."""
    result = DeliveryResult(
        notification_id="n-102",
        channel="sms",
        success=False,
        message="Delivery failed due to bad route",
        error_details="Invalid destination phone number",
    )

    assert result.success is False
    assert result.error_details == "Invalid destination phone number"
    assert result.provider_ref is None


def test_delivery_result_immutability():
    """Verify DeliveryResult cannot be modified after construction."""
    result = DeliveryResult(
        notification_id="n-103",
        channel="slack",
        success=True,
        message="Posted",
    )

    with pytest.raises(FrozenInstanceError):
        result.success = False  # type: ignore[misc]

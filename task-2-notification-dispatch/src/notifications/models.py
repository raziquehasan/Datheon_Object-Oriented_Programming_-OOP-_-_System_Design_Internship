"""
models.py — Core data models for the Notification Dispatch Framework.

Uses Python dataclasses for immutable value objects. All validation
happens in __post_init__ to keep construction simple yet safe.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from notifications.exceptions import InvalidNotificationError


class NotificationPriority(Enum):
    """Priority levels for notifications, ordered from lowest to highest urgency."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True)
class Notification:
    """
    Immutable value object representing a notification to be dispatched.

    Fields
    ------
    notification_id : str
        Unique identifier (UUID4). Auto-generated if not supplied.
    recipient : str
        The address/identifier of the intended recipient (e.g., email, phone number).
    subject : str
        Short headline of the notification.
    body : str
        Full content of the notification message.
    priority : NotificationPriority
        Urgency level; defaults to NORMAL.
    metadata : dict[str, str]
        Arbitrary key-value pairs for routing, tagging, or tracing.
    created_at : datetime
        UTC timestamp of creation; auto-filled.
    """

    recipient: str
    subject: str
    body: str
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: NotificationPriority = NotificationPriority.NORMAL
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Validate that required string fields are non-empty after stripping whitespace."""
        if not isinstance(self.recipient, str) or not self.recipient.strip():
            raise InvalidNotificationError(
                "Notification.recipient must be a non-empty string."
            )
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise InvalidNotificationError(
                "Notification.subject must be a non-empty string."
            )
        if not isinstance(self.body, str) or not self.body.strip():
            raise InvalidNotificationError(
                "Notification.body must be a non-empty string."
            )


@dataclass(frozen=True)
class DeliveryResult:
    """
    Immutable record of the outcome of a single notification delivery attempt.

    Fields
    ------
    notification_id : str
        Matches the originating Notification.notification_id.
    channel : str
        The channel that attempted delivery (e.g., "email", "sms").
    success : bool
        True if the delivery was accepted by the transport.
    message : str
        Human-readable status or error description.
    timestamp : datetime
        UTC timestamp of the delivery attempt; auto-filled.
    provider_ref : str | None
        Optional reference ID returned by the transport provider.
    error_details : str | None
        Machine-readable error context, populated on failure.
    """

    notification_id: str
    channel: str
    success: bool
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provider_ref: str | None = None
    error_details: str | None = None

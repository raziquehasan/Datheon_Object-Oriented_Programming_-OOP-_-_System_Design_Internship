"""
Notification & Alert Dispatch Framework.

A decoupled, SOLID-compliant alert dispatch engine built for
extensibility, offline reliability, and clear architectural boundaries.
"""

from notifications.exceptions import (
    DeliveryError,
    InvalidNotificationError,
    NotificationError,
    SenderConfigurationError,
    UnsupportedChannelError,
)
from notifications.interfaces import NotificationSender, NotificationTransport
from notifications.models import DeliveryResult, Notification, NotificationPriority
from notifications.registry import SenderRegistry
from notifications.service import NotificationService
from notifications.validators import (
    validate_email,
    validate_phone,
    validate_slack_channel,
    validate_whatsapp_number,
)

__version__ = "1.0.0"

__all__ = [
    # Models
    "Notification",
    "NotificationPriority",
    "DeliveryResult",
    # Interfaces
    "NotificationSender",
    "NotificationTransport",
    # Service & Registry
    "NotificationService",
    "SenderRegistry",
    # Exceptions
    "NotificationError",
    "InvalidNotificationError",
    "UnsupportedChannelError",
    "SenderConfigurationError",
    "DeliveryError",
    # Validators
    "validate_email",
    "validate_phone",
    "validate_slack_channel",
    "validate_whatsapp_number",
]

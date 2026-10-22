"""
exceptions.py — Custom exception hierarchy for the Notification Dispatch Framework.

All exceptions inherit from NotificationError, which itself inherits from Exception.
This makes it easy to catch framework-level errors with a single except clause.
"""


class NotificationError(Exception):
    """Base exception for all notification framework errors."""


class InvalidNotificationError(NotificationError):
    """Raised when a Notification object has invalid or missing required fields."""


class UnsupportedChannelError(NotificationError):
    """Raised when a requested notification channel is not registered in the registry."""


class SenderConfigurationError(NotificationError):
    """Raised when a NotificationSender is misconfigured (e.g., invalid Slack channel)."""


class DeliveryError(NotificationError):
    """Raised by a transport layer when delivery fails at the infrastructure level."""

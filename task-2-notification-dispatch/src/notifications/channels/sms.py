"""
sms.py — SMS notification sender and console transport.

Follows Single Responsibility Principle (SRP) by isolating SMS phone validation,
payload summarization, and delegating network transport to an injected adapter.
"""

from __future__ import annotations

import logging
import uuid

from notifications.exceptions import DeliveryError
from notifications.interfaces import NotificationSender, NotificationTransport
from notifications.models import DeliveryResult, Notification
from notifications.validators import validate_phone

logger = logging.getLogger(__name__)


class ConsoleSMSTransport(NotificationTransport):
    """
    Console transport for local/offline SMS testing and demonstration.
    Outputs SMS payloads locally without external cellular/gateway API calls.
    """

    def deliver(self, formatted_payload: str, destination: str) -> tuple[bool, str, str | None]:
        ref_id = f"sms-local-{uuid.uuid4().hex[:8]}"
        logger.info("[ConsoleSMSTransport] Dispatched SMS to %s (ref=%s)", destination, ref_id)
        return True, f"SMS delivered to {destination} via console transport", ref_id


class SMSSender(NotificationSender):
    """
    SMS notification sender implementation.
    Validates E.164-compatible phone numbers, formats a concise text message,
    and delegates transport delivery to an injected NotificationTransport.
    """

    def __init__(self, transport: NotificationTransport) -> None:
        if not isinstance(transport, NotificationTransport):
            raise TypeError("transport must implement NotificationTransport")
        self._transport = transport

    @property
    def channel_name(self) -> str:
        return "sms"

    def send(self, notification: Notification) -> DeliveryResult:
        """
        Validate, format, and deliver an SMS alert.
        Never raises delivery errors; captures all failures in DeliveryResult.
        """
        recipient = notification.recipient.strip() if notification.recipient else ""
        if not validate_phone(recipient):
            return DeliveryResult(
                notification_id=notification.notification_id,
                channel=self.channel_name,
                success=False,
                message=f"Invalid phone recipient for SMS: '{notification.recipient}'",
                error_details="Validation failed: recipient is not an E.164 compliant phone number.",
            )

        formatted_payload = f"[{notification.priority.name}] {notification.subject}: {notification.body}"

        try:
            success, message, provider_ref = self._transport.deliver(
                formatted_payload, destination=recipient
            )
            return DeliveryResult(
                notification_id=notification.notification_id,
                channel=self.channel_name,
                success=success,
                message=message,
                provider_ref=provider_ref,
            )
        except Exception as exc:
            logger.warning("SMS delivery encountered transport failure: %s", exc)
            return DeliveryResult(
                notification_id=notification.notification_id,
                channel=self.channel_name,
                success=False,
                message=f"Transport error during SMS dispatch: {exc}",
                error_details=str(exc),
            )

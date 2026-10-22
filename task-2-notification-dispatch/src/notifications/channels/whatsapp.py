"""
whatsapp.py — WhatsApp alert sender and console transport.

Implements WhatsApp message dispatching with injected transport adapter.
Validates international phone numbers and formats conversational alerts.
"""

from __future__ import annotations

import logging
import uuid

from notifications.exceptions import DeliveryError
from notifications.interfaces import NotificationSender, NotificationTransport
from notifications.models import DeliveryResult, Notification
from notifications.validators import validate_whatsapp_number

logger = logging.getLogger(__name__)


class ConsoleWhatsAppTransport(NotificationTransport):
    """
    Console transport for local/offline WhatsApp testing and demonstration.
    Logs formatted WhatsApp messages without external WhatsApp Business API calls.
    """

    def deliver(self, formatted_payload: str, destination: str) -> tuple[bool, str, str | None]:
        ref_id = f"wa-local-{uuid.uuid4().hex[:8]}"
        logger.info("[ConsoleWhatsAppTransport] Dispatched WhatsApp message to %s (ref=%s)", destination, ref_id)
        return True, f"WhatsApp message delivered to {destination} via console transport", ref_id


class WhatsAppSender(NotificationSender):
    """
    WhatsApp notification sender implementation.
    Validates international phone number, applies WhatsApp markdown formatting,
    and delegates physical delivery to an injected NotificationTransport.
    """

    def __init__(self, transport: NotificationTransport) -> None:
        if not isinstance(transport, NotificationTransport):
            raise TypeError("transport must implement NotificationTransport")
        self._transport = transport

    @property
    def channel_name(self) -> str:
        return "whatsapp"

    def send(self, notification: Notification) -> DeliveryResult:
        """
        Validate, format, and deliver a WhatsApp notification.
        Never raises delivery errors; captures all failures in DeliveryResult.
        """
        recipient = notification.recipient.strip() if notification.recipient else ""
        if not validate_whatsapp_number(recipient):
            return DeliveryResult(
                notification_id=notification.notification_id,
                channel=self.channel_name,
                success=False,
                message=f"Invalid WhatsApp recipient number: '{notification.recipient}'",
                error_details="Validation failed: WhatsApp recipient must be an E.164 international phone number.",
            )

        formatted_payload = (
            f"*[{notification.priority.name}] {notification.subject}*\n\n"
            f"{notification.body}"
        )

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
            logger.warning("WhatsApp delivery encountered transport failure: %s", exc)
            return DeliveryResult(
                notification_id=notification.notification_id,
                channel=self.channel_name,
                success=False,
                message=f"Transport error during WhatsApp dispatch: {exc}",
                error_details=str(exc),
            )

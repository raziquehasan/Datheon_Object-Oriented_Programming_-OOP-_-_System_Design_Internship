"""
slack.py — Slack alert sender and console transport.

Implements Slack webhook/channel notification handling with injected transport.
Validates Slack channel/user identifier (#channel or @user).
"""

from __future__ import annotations

import logging
import uuid

from notifications.exceptions import DeliveryError, SenderConfigurationError
from notifications.interfaces import NotificationSender, NotificationTransport
from notifications.models import DeliveryResult, Notification
from notifications.validators import validate_slack_channel

logger = logging.getLogger(__name__)


class ConsoleSlackTransport(NotificationTransport):
    """
    Console transport for local/offline Slack testing and demonstration.
    Logs Slack payload formatted for channel/webhook delivery.
    """

    def deliver(self, formatted_payload: str, destination: str) -> tuple[bool, str, str | None]:
        ref_id = f"slack-local-{uuid.uuid4().hex[:8]}"
        logger.info("[ConsoleSlackTransport] Posted to Slack destination %s (ref=%s)", destination, ref_id)
        return True, f"Slack message posted to {destination} via console transport", ref_id


class SlackSender(NotificationSender):
    """
    Slack notification sender implementation.
    Validates configured default channel/destination on instantiation,
    formats message payloads, and delegates delivery to NotificationTransport.
    """

    def __init__(self, channel_destination: str, transport: NotificationTransport) -> None:
        if not isinstance(transport, NotificationTransport):
            raise TypeError("transport must implement NotificationTransport")
        if not validate_slack_channel(channel_destination):
            raise SenderConfigurationError(
                f"Invalid Slack channel destination: '{channel_destination}'. Must start with '#' or '@'."
            )
        self._channel_destination = channel_destination
        self._transport = transport

    @property
    def channel_name(self) -> str:
        return "slack"

    @property
    def default_destination(self) -> str:
        return self._channel_destination

    def send(self, notification: Notification) -> DeliveryResult:
        """
        Validate recipient destination, format Slack message, and deliver.
        Never raises delivery errors; captures all failures in DeliveryResult.
        """
        target = notification.recipient.strip() if notification.recipient else ""

        # If recipient is provided, it must be a valid Slack destination (#channel or @user).
        # If recipient equals default or is valid slack format, accept it.
        # Otherwise, validate target.
        if not validate_slack_channel(target):
            return DeliveryResult(
                notification_id=notification.notification_id,
                channel=self.channel_name,
                success=False,
                message=f"Invalid Slack destination: '{notification.recipient}'",
                error_details="Validation failed: Slack target must start with '#' or '@' followed by an identifier.",
            )

        formatted_payload = (
            f"Slack Destination: {target}\n"
            f"Priority: {notification.priority.name}\n"
            f"Title: {notification.subject}\n"
            f"Message: {notification.body}"
        )

        try:
            success, message, provider_ref = self._transport.deliver(
                formatted_payload, destination=target
            )
            return DeliveryResult(
                notification_id=notification.notification_id,
                channel=self.channel_name,
                success=success,
                message=message,
                provider_ref=provider_ref,
            )
        except Exception as exc:
            logger.warning("Slack delivery encountered transport failure: %s", exc)
            return DeliveryResult(
                notification_id=notification.notification_id,
                channel=self.channel_name,
                success=False,
                message=f"Transport error during Slack dispatch: {exc}",
                error_details=str(exc),
            )

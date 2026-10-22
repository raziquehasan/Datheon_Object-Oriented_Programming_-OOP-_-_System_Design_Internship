"""
service.py — High-level notification dispatch coordinator.

Demonstrates:
- Single Responsibility: Orchestrating dispatch and aggregating results only.
- Dependency Inversion: Depends on SenderRegistry abstraction, not concrete senders.
- Open/Closed: New channels can be handled without modifying this service.
"""

from __future__ import annotations

import logging
from typing import List, Sequence

from notifications.exceptions import UnsupportedChannelError
from notifications.models import DeliveryResult, Notification
from notifications.registry import SenderRegistry

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Coordinates notification dispatch across registered channels.

    Dependencies are injected via constructor (SenderRegistry).
    """

    def __init__(self, registry: SenderRegistry) -> None:
        if not isinstance(registry, SenderRegistry):
            raise TypeError(f"Expected SenderRegistry instance, got {type(registry).__name__}")
        self._registry = registry

    @property
    def registry(self) -> SenderRegistry:
        """Access the underlying channel registry."""
        return self._registry

    def send(self, notification: Notification, channel: str) -> DeliveryResult:
        """
        Send a notification through a single specified channel.

        Parameters
        ----------
        notification : Notification
            The validated notification to send.
        channel : str
            Identifier of the target channel (e.g., 'email', 'sms').

        Returns
        -------
        DeliveryResult
            The outcome of the delivery attempt.

        Raises
        ------
        UnsupportedChannelError
            If the requested channel is not registered.
        """
        sender = self._registry.get(channel)
        logger.info(
            "Dispatching notification %s via channel '%s'",
            notification.notification_id,
            channel,
        )

        result = sender.send(notification)

        if result.success:
            logger.info(
                "Successfully delivered notification %s via channel '%s'",
                notification.notification_id,
                channel,
            )
        else:
            logger.warning(
                "Delivery failed for notification %s on channel '%s': %s",
                notification.notification_id,
                channel,
                result.message,
            )

        return result

    def dispatch(
        self, notification: Notification, channels: Sequence[str]
    ) -> List[DeliveryResult]:
        """
        Dispatch a notification across multiple channels simultaneously.

        Supports partial success: if one channel fails or is unsupported,
        other channels continue to be processed.
        Unsupported channels are captured as unsuccessful DeliveryResult records
        rather than raising an exception, ensuring callers receive comprehensive
        feedback across all attempted targets.

        Parameters
        ----------
        notification : Notification
            The notification to dispatch.
        channels : Sequence[str]
            List or sequence of channel identifiers to target.

        Returns
        -------
        List[DeliveryResult]
            Structured results for each attempted channel in order.
        """
        results: List[DeliveryResult] = []

        for ch in channels:
            try:
                result = self.send(notification, ch)
                results.append(result)
            except UnsupportedChannelError as exc:
                logger.warning(
                    "Channel '%s' is not registered for notification %s",
                    ch,
                    notification.notification_id,
                )
                results.append(
                    DeliveryResult(
                        notification_id=notification.notification_id,
                        channel=ch,
                        success=False,
                        message=f"Unsupported channel: '{ch}'",
                        error_details=str(exc),
                    )
                )

        return results

"""
interfaces.py — Abstract base classes defining the contracts for the framework.

These ABCs enforce the Dependency Inversion Principle (DIP) — high-level
modules depend on these abstractions, never on concrete implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from notifications.models import DeliveryResult, Notification


class NotificationTransport(ABC):
    """
    Low-level transport abstraction responsible for physically delivering a
    pre-formatted payload to a destination address.

    Concrete implementations might wrap SMTP, Twilio, Slack SDK, etc.
    For testing and demo purposes, console implementations are provided.
    """

    @abstractmethod
    def deliver(self, formatted_payload: str, destination: str) -> tuple[bool, str, str | None]:
        """
        Deliver the payload to the given destination.

        Parameters
        ----------
        formatted_payload : str
            The fully formatted message string ready for transmission.
        destination : str
            The target address (email, phone number, Slack channel, etc.).

        Returns
        -------
        tuple[bool, str, str | None]
            A 3-tuple of (success, human_readable_message, provider_ref_or_none).
        """


class NotificationSender(ABC):
    """
    High-level sender abstraction that knows how to validate, format, and
    dispatch a Notification via a specific channel.

    Concrete senders compose a NotificationTransport for actual delivery,
    keeping formatting logic separate from transport logic (SRP).
    """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """
        Return the unique identifier for this channel, e.g. 'email', 'sms'.

        Used as the key when registering with SenderRegistry.
        """

    @abstractmethod
    def send(self, notification: Notification) -> DeliveryResult:
        """
        Send a notification via this channel.

        Must NEVER raise on delivery failure — all errors must be captured
        and returned as a DeliveryResult with success=False.

        Parameters
        ----------
        notification : Notification
            The notification to dispatch.

        Returns
        -------
        DeliveryResult
            The outcome of the delivery attempt.
        """

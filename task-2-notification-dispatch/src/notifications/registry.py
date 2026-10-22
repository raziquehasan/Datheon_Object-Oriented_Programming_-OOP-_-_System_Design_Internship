"""
registry.py — Registry for NotificationSender implementations.

Demonstrates the Open/Closed Principle (OCP) and Dependency Inversion Principle (DIP):
the registry depends strictly on the NotificationSender abstraction, allowing new
channels to be registered dynamically without modifying existing framework code.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from notifications.exceptions import UnsupportedChannelError
from notifications.interfaces import NotificationSender

logger = logging.getLogger(__name__)


class SenderRegistry:
    """
    Central registry mapping channel identifiers to NotificationSender instances.

    Does not import or depend on concrete channel implementations.
    """

    def __init__(self) -> None:
        self._senders: Dict[str, NotificationSender] = {}

    def _extract_channel_name(self, sender: NotificationSender) -> str:
        """Extract and normalize channel name whether defined as property or method."""
        raw_name = sender.channel_name() if callable(sender.channel_name) else sender.channel_name
        if not raw_name or not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("Sender must provide a non-empty string channel_name.")
        return raw_name.strip().lower()

    def register(self, sender: NotificationSender, overwrite: bool = False) -> None:
        """
        Register a notification sender implementation.

        Parameters
        ----------
        sender : NotificationSender
            The sender implementation to register.
        overwrite : bool
            If True, permits replacing an already registered channel sender.
            If False (default), raises ValueError on collision.

        Raises
        ------
        TypeError
            If sender does not implement NotificationSender.
        ValueError
            If channel name is already registered and overwrite is False,
            or if channel name is invalid.
        """
        if not isinstance(sender, NotificationSender):
            raise TypeError(
                f"Expected instance of NotificationSender, got {type(sender).__name__}"
            )

        channel = self._extract_channel_name(sender)

        if channel in self._senders and not overwrite:
            raise ValueError(
                f"Channel '{channel}' is already registered. "
                "Pass overwrite=True if you intend to replace the existing sender."
            )

        self._senders[channel] = sender
        logger.info("Registered notification sender for channel '%s'", channel)

    def get(self, channel_name: str) -> NotificationSender:
        """
        Retrieve the sender registered for the specified channel name.

        Parameters
        ----------
        channel_name : str
            Identifier of the desired channel (case-insensitive).

        Returns
        -------
        NotificationSender
            The registered sender instance.

        Raises
        ------
        UnsupportedChannelError
            If no sender is registered for the given channel.
        """
        if not channel_name or not isinstance(channel_name, str):
            raise UnsupportedChannelError("Channel name must be a non-empty string.")

        normalized = channel_name.strip().lower()
        if normalized not in self._senders:
            raise UnsupportedChannelError(
                f"Channel '{channel_name}' is not registered or supported. "
                f"Available channels: {self.registered_channels()}"
            )

        return self._senders[normalized]

    def unregister(self, channel_name: str) -> None:
        """
        Remove a sender from the registry.

        Parameters
        ----------
        channel_name : str
            Identifier of the channel to unregister.

        Raises
        ------
        UnsupportedChannelError
            If the channel is not currently registered.
        """
        if not channel_name or not isinstance(channel_name, str):
            raise UnsupportedChannelError("Channel name must be a non-empty string.")

        normalized = channel_name.strip().lower()
        if normalized not in self._senders:
            raise UnsupportedChannelError(
                f"Cannot unregister: channel '{channel_name}' is not registered."
            )

        del self._senders[normalized]
        logger.info("Unregistered notification sender for channel '%s'", normalized)

    def registered_channels(self) -> List[str]:
        """
        Return an alphabetically sorted list of registered channel names.
        """
        return sorted(self._senders.keys())

    def __contains__(self, channel_name: str) -> bool:
        if not channel_name or not isinstance(channel_name, str):
            return False
        return channel_name.strip().lower() in self._senders

    def __len__(self) -> int:
        return len(self._senders)

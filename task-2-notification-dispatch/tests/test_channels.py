"""
test_channels.py — Comprehensive unit tests for all notification channels.

Covers Email, SMS, Slack, and WhatsApp senders along with their offline transports,
recipient validation, error capture, and exception resilience.
"""

from __future__ import annotations

import pytest

from notifications.channels.email import ConsoleEmailTransport, EmailSender
from notifications.channels.slack import ConsoleSlackTransport, SlackSender
from notifications.channels.sms import ConsoleSMSTransport, SMSSender
from notifications.channels.whatsapp import ConsoleWhatsAppTransport, WhatsAppSender
from notifications.exceptions import DeliveryError, SenderConfigurationError
from notifications.interfaces import NotificationTransport
from notifications.models import Notification, NotificationPriority
from notifications.validators import (
    validate_email,
    validate_phone,
    validate_slack_channel,
    validate_whatsapp_number,
)


# ============================================================================
# Fake Transports for Deterministic Testing
# ============================================================================

class MockSuccessTransport(NotificationTransport):
    """A transport that records delivery calls and returns success."""

    def __init__(self, provider_ref: str = "mock-ref-100") -> None:
        self.calls: list[tuple[str, str]] = []
        self._provider_ref = provider_ref

    def deliver(self, formatted_payload: str, destination: str) -> tuple[bool, str, str | None]:
        self.calls.append((formatted_payload, destination))
        return True, f"Mock delivered to {destination}", self._provider_ref


class MockFailingTransport(NotificationTransport):
    """A transport that raises an exception during delivery."""

    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc or DeliveryError("Mock transport simulated network dropout")

    def deliver(self, formatted_payload: str, destination: str) -> tuple[bool, str, str | None]:
        raise self._exc


# ============================================================================
# Validator Tests
# ============================================================================

def test_validate_email_valid_and_invalid():
    assert validate_email("user@example.com") is True
    assert validate_email("first.last+tag@sub.domain.org") is True
    assert validate_email("invalid-email") is False
    assert validate_email("@no-local.com") is False
    assert validate_email("no-domain@") is False
    assert validate_email("no-tld@domain") is False
    assert validate_email(None) is False  # type: ignore[arg-type]


def test_validate_phone_valid_and_invalid():
    assert validate_phone("+14155552671") is True
    assert validate_phone("919876543210") is True
    assert validate_phone("+442071838750") is True
    assert validate_phone("12345") is False  # too short (< 7 digits)
    assert validate_phone("+12345678901234567") is False  # too long (> 15 digits)
    assert validate_phone("+1415abc5555") is False
    assert validate_phone("") is False
    assert validate_phone(None) is False  # type: ignore[arg-type]


def test_validate_slack_channel_valid_and_invalid():
    assert validate_slack_channel("#general") is True
    assert validate_slack_channel("#alerts-prod") is True
    assert validate_slack_channel("@john.doe") is True
    assert validate_slack_channel("#") is False
    assert validate_slack_channel("@") is False
    assert validate_slack_channel("general") is False  # missing prefix
    assert validate_slack_channel("") is False
    assert validate_slack_channel(None) is False  # type: ignore[arg-type]


def test_validate_whatsapp_number():
    assert validate_whatsapp_number("+14155552671") is True
    assert validate_whatsapp_number("+919876543210") is True
    assert validate_whatsapp_number("not-a-number") is False


# ============================================================================
# Email Channel Tests
# ============================================================================

def test_email_sender_success_with_mock_transport():
    transport = MockSuccessTransport()
    sender = EmailSender(transport=transport)
    assert sender.channel_name == "email"

    notif = Notification(
        recipient="alice@datheon.io",
        subject="Deployment Succeeded",
        body="Service v2.4 is healthy.",
        priority=NotificationPriority.HIGH,
    )

    result = sender.send(notif)
    assert result.success is True
    assert result.channel == "email"
    assert result.notification_id == notif.notification_id
    assert "Mock delivered to alice@datheon.io" in result.message
    assert result.provider_ref == "mock-ref-100"
    assert len(transport.calls) == 1
    assert "Deployment Succeeded" in transport.calls[0][0]


def test_email_sender_invalid_recipient():
    transport = MockSuccessTransport()
    sender = EmailSender(transport=transport)

    notif = Notification(
        recipient="not-a-valid-email",
        subject="Test",
        body="Body",
    )

    result = sender.send(notif)
    assert result.success is False
    assert result.channel == "email"
    assert "Invalid email recipient" in result.message
    assert len(transport.calls) == 0  # Transport never invoked


def test_email_sender_handles_transport_exception():
    transport = MockFailingTransport(DeliveryError("SMTP connection timed out"))
    sender = EmailSender(transport=transport)

    notif = Notification(
        recipient="bob@datheon.io",
        subject="Alert",
        body="Body",
    )

    result = sender.send(notif)
    assert result.success is False
    assert "Transport error" in result.message
    assert "SMTP connection timed out" in (result.error_details or "")


def test_email_sender_console_transport_offline():
    transport = ConsoleEmailTransport()
    sender = EmailSender(transport=transport)

    notif = Notification(
        recipient="dev@example.com",
        subject="Offline Test",
        body="Checking console transport",
    )

    result = sender.send(notif)
    assert result.success is True
    assert "via console transport" in result.message
    assert result.provider_ref is not None
    assert result.provider_ref.startswith("email-local-")


def test_email_sender_requires_valid_transport():
    with pytest.raises(TypeError, match="must implement NotificationTransport"):
        EmailSender(transport="not-a-transport")  # type: ignore[arg-type]


# ============================================================================
# SMS Channel Tests
# ============================================================================

def test_sms_sender_success():
    transport = MockSuccessTransport(provider_ref="sms-tx-200")
    sender = SMSSender(transport=transport)
    assert sender.channel_name == "sms"

    notif = Notification(
        recipient="+14155552671",
        subject="OTP Code",
        body="Your code is 849201",
        priority=NotificationPriority.CRITICAL,
    )

    result = sender.send(notif)
    assert result.success is True
    assert result.channel == "sms"
    assert result.provider_ref == "sms-tx-200"
    assert len(transport.calls) == 1
    assert "CRITICAL" in transport.calls[0][0]


def test_sms_sender_invalid_phone():
    transport = MockSuccessTransport()
    sender = SMSSender(transport=transport)

    notif = Notification(
        recipient="invalid-phone-abc",
        subject="Test",
        body="Body",
    )

    result = sender.send(notif)
    assert result.success is False
    assert "Invalid phone recipient" in result.message
    assert len(transport.calls) == 0


def test_sms_sender_transport_exception():
    transport = MockFailingTransport(RuntimeError("SMS Gateway 503"))
    sender = SMSSender(transport=transport)

    notif = Notification(
        recipient="+919876543210",
        subject="Test",
        body="Body",
    )

    result = sender.send(notif)
    assert result.success is False
    assert "SMS Gateway 503" in (result.error_details or "")


def test_sms_console_transport():
    transport = ConsoleSMSTransport()
    sender = SMSSender(transport=transport)

    notif = Notification(
        recipient="+14155552671",
        subject="Ping",
        body="Pong",
    )

    result = sender.send(notif)
    assert result.success is True
    assert result.provider_ref is not None
    assert result.provider_ref.startswith("sms-local-")


def test_sms_sender_requires_valid_transport():
    with pytest.raises(TypeError, match="must implement NotificationTransport"):
        SMSSender(transport=None)  # type: ignore[arg-type]


# ============================================================================
# Slack Channel Tests
# ============================================================================

def test_slack_sender_constructor_validation():
    transport = MockSuccessTransport()

    # Valid destinations
    sender1 = SlackSender(channel_destination="#dev-ops", transport=transport)
    assert sender1.channel_name == "slack"
    assert sender1.default_destination == "#dev-ops"

    sender2 = SlackSender(channel_destination="@incident-commander", transport=transport)
    assert sender2.default_destination == "@incident-commander"

    # Invalid destination raises SenderConfigurationError
    with pytest.raises(SenderConfigurationError, match="Invalid Slack channel destination"):
        SlackSender(channel_destination="no-hash-or-at", transport=transport)

    with pytest.raises(SenderConfigurationError):
        SlackSender(channel_destination="#", transport=transport)

    with pytest.raises(TypeError):
        SlackSender(channel_destination="#alerts", transport="bad-transport")  # type: ignore[arg-type]


def test_slack_sender_success_with_valid_destination():
    transport = MockSuccessTransport(provider_ref="slack-msg-300")
    sender = SlackSender(channel_destination="#alerts", transport=transport)

    notif = Notification(
        recipient="#alerts",
        subject="High CPU Usage",
        body="Host server-01 CPU > 95%",
        priority=NotificationPriority.HIGH,
    )

    result = sender.send(notif)
    assert result.success is True
    assert result.channel == "slack"
    assert result.provider_ref == "slack-msg-300"
    assert len(transport.calls) == 1
    assert "Slack Destination: #alerts" in transport.calls[0][0]


def test_slack_sender_invalid_recipient():
    transport = MockSuccessTransport()
    sender = SlackSender(channel_destination="#alerts", transport=transport)

    notif = Notification(
        recipient="plain-text-name",
        subject="Alert",
        body="Body",
    )

    result = sender.send(notif)
    assert result.success is False
    assert "Invalid Slack destination" in result.message
    assert len(transport.calls) == 0


def test_slack_sender_transport_exception():
    transport = MockFailingTransport(DeliveryError("Slack API rate limited"))
    sender = SlackSender(channel_destination="#general", transport=transport)

    notif = Notification(
        recipient="#general",
        subject="Rate limit test",
        body="Body",
    )

    result = sender.send(notif)
    assert result.success is False
    assert "Slack API rate limited" in (result.error_details or "")


def test_slack_console_transport():
    transport = ConsoleSlackTransport()
    sender = SlackSender(channel_destination="#on-call", transport=transport)

    notif = Notification(
        recipient="#on-call",
        subject="Console Slack",
        body="Checking console Slack delivery",
    )

    result = sender.send(notif)
    assert result.success is True
    assert result.provider_ref is not None
    assert result.provider_ref.startswith("slack-local-")


# ============================================================================
# WhatsApp Channel Tests
# ============================================================================

def test_whatsapp_sender_success():
    transport = MockSuccessTransport(provider_ref="wa-msg-400")
    sender = WhatsAppSender(transport=transport)
    assert sender.channel_name == "whatsapp"

    notif = Notification(
        recipient="+14155552671",
        subject="Security Notice",
        body="New login from Chrome / macOS",
        priority=NotificationPriority.HIGH,
    )

    result = sender.send(notif)
    assert result.success is True
    assert result.channel == "whatsapp"
    assert result.provider_ref == "wa-msg-400"
    assert len(transport.calls) == 1
    assert "*[HIGH] Security Notice*" in transport.calls[0][0]


def test_whatsapp_sender_invalid_phone():
    transport = MockSuccessTransport()
    sender = WhatsAppSender(transport=transport)

    notif = Notification(
        recipient="not-a-phone-number",
        subject="Test",
        body="Body",
    )

    result = sender.send(notif)
    assert result.success is False
    assert "Invalid WhatsApp recipient" in result.message
    assert len(transport.calls) == 0


def test_whatsapp_sender_transport_exception():
    transport = MockFailingTransport(DeliveryError("WhatsApp Cloud API timeout"))
    sender = WhatsAppSender(transport=transport)

    notif = Notification(
        recipient="+14155552671",
        subject="Test",
        body="Body",
    )

    result = sender.send(notif)
    assert result.success is False
    assert "WhatsApp Cloud API timeout" in (result.error_details or "")


def test_whatsapp_console_transport():
    transport = ConsoleWhatsAppTransport()
    sender = WhatsAppSender(transport=transport)

    notif = Notification(
        recipient="+14155552671",
        subject="WhatsApp Test",
        body="Testing console transport",
    )

    result = sender.send(notif)
    assert result.success is True
    assert result.provider_ref is not None
    assert result.provider_ref.startswith("wa-local-")


def test_whatsapp_sender_requires_valid_transport():
    with pytest.raises(TypeError, match="must implement NotificationTransport"):
        WhatsAppSender(transport=12345)  # type: ignore[arg-type]

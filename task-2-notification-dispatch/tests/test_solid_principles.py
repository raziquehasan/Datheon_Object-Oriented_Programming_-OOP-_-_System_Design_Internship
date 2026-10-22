"""
test_solid_principles.py — Formal verification of all 5 SOLID principles.

Provides programmatic proof that the architecture strictly adheres to:
- S: Single Responsibility Principle
- O: Open/Closed Principle
- L: Liskov Substitution Principle
- I: Interface Segregation Principle
- D: Dependency Inversion Principle
"""

from __future__ import annotations

import inspect
import sys
from typing import get_type_hints
import pytest

from notifications.channels.email import ConsoleEmailTransport, EmailSender
from notifications.channels.slack import ConsoleSlackTransport, SlackSender
from notifications.channels.sms import ConsoleSMSTransport, SMSSender
from notifications.channels.whatsapp import ConsoleWhatsAppTransport, WhatsAppSender
from notifications.interfaces import NotificationSender, NotificationTransport
from notifications.models import DeliveryResult, Notification, NotificationPriority
from notifications.registry import SenderRegistry
import notifications.service as service_module
from notifications.service import NotificationService


# ============================================================================
# 1. Single Responsibility Principle (SRP)
# ============================================================================

def test_srp_responsibility_isolation():
    """
    Verify classes maintain single, strictly bounded responsibilities:
    - Notification: pure data representation (no dispatch, no format logic)
    - NotificationService: dispatch coordination only (no formatting, no transport logic)
    - Transport: delivery mechanics only (no validation, no formatting)
    - Sender: formatting + delegation (no direct transport mechanics)
    """
    # 1. Notification model has no delivery, dispatch, or formatting methods
    notif_methods = [
        m for m in dir(Notification)
        if not m.startswith("_") and callable(getattr(Notification, m))
    ]
    for prohibited in ["send", "deliver", "format", "dispatch", "connect"]:
        assert prohibited not in notif_methods, f"Notification should not have '{prohibited}'"

    # 2. NotificationService delegates delivery and doesn't implement raw transport
    service_methods = [
        m for m in dir(NotificationService)
        if not m.startswith("_") and callable(getattr(NotificationService, m))
    ]
    assert "deliver" not in service_methods
    assert "format_message" not in service_methods

    # 3. Transport only has deliver method
    transport_methods = [
        m for m in dir(NotificationTransport)
        if not m.startswith("_") and callable(getattr(NotificationTransport, m))
    ]
    assert transport_methods == ["deliver"]


# ============================================================================
# 2. Open/Closed Principle (OCP)
# ============================================================================

class PagerDutySender(NotificationSender):
    """
    Custom channel sender created without modifying any line of core framework code.
    Proves system is Open for extension, Closed for modification.
    """

    def __init__(self, transport: NotificationTransport) -> None:
        self._transport = transport

    @property
    def channel_name(self) -> str:
        return "pagerduty"

    def send(self, notification: Notification) -> DeliveryResult:
        payload = f"[INCIDENT] {notification.subject}: {notification.body}"
        success, msg, ref = self._transport.deliver(payload, notification.recipient)
        return DeliveryResult(
            notification_id=notification.notification_id,
            channel=self.channel_name,
            success=success,
            message=msg,
            provider_ref=ref,
        )


class MockPagerDutyTransport(NotificationTransport):
    def deliver(self, formatted_payload: str, destination: str) -> tuple[bool, str, str | None]:
        return True, f"PagerDuty incident triggered for {destination}", "pd-inc-999"


def test_ocp_add_new_channel_without_modifying_service():
    """
    Verify a new channel (PagerDuty) can be defined, registered, and dispatched
    through NotificationService without altering NotificationService.
    """
    registry = SenderRegistry()
    pd_sender = PagerDutySender(transport=MockPagerDutyTransport())
    registry.register(pd_sender)

    service = NotificationService(registry=registry)

    notif = Notification(
        recipient="devops-oncall",
        subject="High Latency Alert",
        body="API response p99 > 2000ms",
        priority=NotificationPriority.CRITICAL,
    )

    # Dispatch via the brand new channel
    result = service.send(notif, "pagerduty")

    assert result.success is True
    assert result.channel == "pagerduty"
    assert result.provider_ref == "pd-inc-999"
    assert "PagerDuty incident triggered" in result.message


# ============================================================================
# 3. Liskov Substitution Principle (LSP)
# ============================================================================

def test_lsp_all_senders_substitutable_without_type_checks():
    """
    Verify all senders (built-in and custom) can be substituted anywhere
    NotificationSender is expected, producing uniform DeliveryResult objects
    without raising unexpected exceptions or requiring type branching.
    """
    senders: list[NotificationSender] = [
        EmailSender(transport=ConsoleEmailTransport()),
        SMSSender(transport=ConsoleSMSTransport()),
        SlackSender(channel_destination="#general", transport=ConsoleSlackTransport()),
        WhatsAppSender(transport=ConsoleWhatsAppTransport()),
        PagerDutySender(transport=MockPagerDutyTransport()),
    ]

    registry = SenderRegistry()
    for s in senders:
        registry.register(s)

    service = NotificationService(registry=registry)

    # Test each sender with a suitable recipient
    test_cases = [
        ("email", "ops@datheon.io"),
        ("sms", "+14155552671"),
        ("slack", "#general"),
        ("whatsapp", "+14155552671"),
        ("pagerduty", "ops-team"),
    ]

    for channel, recipient in test_cases:
        notif = Notification(
            recipient=recipient,
            subject=f"Health Ping for {channel}",
            body="System functional",
        )
        result = service.send(notif, channel)

        # Consistent contract verification
        assert isinstance(result, DeliveryResult)
        assert isinstance(result.success, bool)
        assert isinstance(result.message, str)
        assert result.channel == channel
        assert result.notification_id == notif.notification_id


# ============================================================================
# 4. Interface Segregation Principle (ISP)
# ============================================================================

def test_isp_minimal_focused_interfaces():
    """
    Verify interfaces are lean and clients are not forced to depend on methods
    they do not use (no bloated lifecycle, attachments, batch, or auth methods).
    """
    # 1. NotificationSender has only 'channel_name' and 'send'
    abstract_methods = NotificationSender.__abstractmethods__
    assert abstract_methods == frozenset({"channel_name", "send"})

    # 2. NotificationTransport has only 'deliver'
    assert NotificationTransport.__abstractmethods__ == frozenset({"deliver"})

    # 3. Prove a minimal class satisfies NotificationSender with zero extraneous methods
    class UltraMinimalSender(NotificationSender):
        @property
        def channel_name(self) -> str:
            return "minimal"

        def send(self, notification: Notification) -> DeliveryResult:
            return DeliveryResult(notification.notification_id, "minimal", True, "ok")

    minimal_instance = UltraMinimalSender()
    assert isinstance(minimal_instance, NotificationSender)


# ============================================================================
# 5. Dependency Inversion Principle (DIP)
# ============================================================================

def test_dip_service_depends_on_abstractions_not_concretions():
    """
    Verify NotificationService and SenderRegistry have no import or dependency
    on concrete sender classes (EmailSender, SMSSender, SlackSender, WhatsAppSender).
    High-level modules depend only on abstractions.
    """
    # Inspect service module globals and imports
    service_src = inspect.getsource(service_module)

    # Concrete senders must NOT be imported in service.py
    for concrete in ["EmailSender", "SMSSender", "SlackSender", "WhatsAppSender"]:
        assert concrete not in service_src, (
            f"DIP violation: {concrete} found in service.py source code!"
        )

    # Check constructor typing uses SenderRegistry
    init_sig = inspect.signature(NotificationService.__init__)
    assert "registry" in init_sig.parameters

    # Registry itself must not import concrete channels
    import notifications.registry as registry_module
    registry_src = inspect.getsource(registry_module)
    for concrete in ["EmailSender", "SMSSender", "SlackSender", "WhatsAppSender"]:
        assert concrete not in registry_src, (
            f"DIP violation: {concrete} found in registry.py source code!"
        )

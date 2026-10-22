#!/usr/bin/env python3
"""
Task 2 Demonstration — SOLID Notification & Alert Dispatch Framework.

Runs 100% offline using local console transports.
Demonstrates:
- Notification model creation & validation
- Channel registration (Email, SMS, Slack, WhatsApp)
- Open/Closed Principle via custom PushNotificationSender registration
- Multi-channel dispatch orchestration
- Error handling with unsupported channels and invalid recipients
- Dependency Injection through SenderRegistry
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

# Add src to python path for standalone execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from notifications import (
    DeliveryResult,
    Notification,
    NotificationPriority,
    NotificationSender,
    NotificationService,
    SenderRegistry,
    UnsupportedChannelError,
)
from notifications.channels import (
    ConsoleEmailTransport,
    ConsoleSlackTransport,
    ConsoleSMSTransport,
    ConsoleWhatsAppTransport,
    EmailSender,
    SlackSender,
    SMSSender,
    WhatsAppSender,
)


class PushNotificationSender(NotificationSender):
    """
    Custom Push Notification channel demonstrating the Open/Closed Principle (OCP).
    Added without modifying any existing service or channel code.
    """

    @property
    def channel_name(self) -> str:
        return "push"

    def send(self, notification: Notification) -> DeliveryResult:
        print(f"  [DEVICE-GATEWAY] Push payload delivered to: {notification.recipient}")
        return DeliveryResult(
            notification_id=notification.notification_id,
            channel=self.channel_name,
            success=True,
            message="Push notification delivered to device (local demo transport)",
            provider_ref="apns-fcm-local-demo",
        )


def main() -> None:
    print("=" * 72)
    print(" DATHEON OOP & SYSTEM DESIGN INTERNSHIP -- TASK 2 DEMO")
    print(" SOLID Notification & Alert Dispatch Framework (Offline Mode)")
    print("=" * 72)

    # 1. Initialize Registry and Register All Standard Channels
    print("\n[Step 1] Initializing Registry and Registering Standard Channels...")
    registry = SenderRegistry()
    registry.register(EmailSender(transport=ConsoleEmailTransport()))
    registry.register(SMSSender(transport=ConsoleSMSTransport()))
    registry.register(SlackSender(channel_destination="#production-alerts", transport=ConsoleSlackTransport()))
    registry.register(WhatsAppSender(transport=ConsoleWhatsAppTransport()))

    # 2. Register Custom Channel (Open/Closed Principle)
    print("\n[Step 2] Extending Engine with Custom Channel ('push') -- OCP in action...")
    registry.register(PushNotificationSender())

    print(f"  --> Registered Channels: {', '.join(registry.registered_channels())}")

    # 3. Instantiate Service via Dependency Injection
    print("\n[Step 3] Initializing NotificationService via Dependency Injection...")
    service = NotificationService(registry=registry)

    # 4. Dispatch Multi-Channel Notifications
    print("\n[Step 4] Dispatching Targeted Notifications across Channels...")
    print("-" * 72)

    notifications_to_send = [
        ("email", Notification(
            recipient="sre-team@datheon.io",
            subject="Service Latency Spike",
            body="API p99 latency exceeded 1500ms threshold in region us-east.",
            priority=NotificationPriority.HIGH,
            metadata={"environment": "production", "service": "api-gateway"},
        )),
        ("sms", Notification(
            recipient="+14155552671",
            subject="P1 Incident",
            body="Database failover initiated. Standby replica promoted.",
            priority=NotificationPriority.CRITICAL,
        )),
        ("slack", Notification(
            recipient="#production-alerts",
            subject="Deployment Finished",
            body="Build v3.12.0 deployed successfully to cluster-01.",
            priority=NotificationPriority.NORMAL,
        )),
        ("whatsapp", Notification(
            recipient="+919876543210",
            subject="On-Call Shift",
            body="Your scheduled on-call rotation begins in 30 minutes.",
            priority=NotificationPriority.LOW,
        )),
        ("push", Notification(
            recipient="device-token-f91b-83c2",
            subject="Security Ping",
            body="New sign-in detected on Web App.",
            priority=NotificationPriority.NORMAL,
        )),
    ]

    for channel, notif in notifications_to_send:
        print(f"\nDispatching to channel: [{channel.upper()}]")
        print(f"  Target: {notif.recipient}")
        print(f"  Title:  [{notif.priority.name}] {notif.subject}")
        result = service.send(notif, channel)
        status_symbol = "[SUCCESS]" if result.success else "[FAILED]"
        print(f"  Status: {status_symbol} -> {result.message}")
        if result.provider_ref:
            print(f"  Ref ID: {result.provider_ref}")

    # 5. Multi-Channel Batch Dispatch with Partial Failure Handling
    print("\n" + "-" * 72)
    print("[Step 5] Multi-Channel Batch Dispatch (Handling Partial Failures)...")
    broadcast_notif = Notification(
        recipient="+14155552671",
        subject="Maintenance Window",
        body="Scheduled maintenance starting at 02:00 UTC.",
        priority=NotificationPriority.NORMAL,
    )

    batch_channels = ["sms", "whatsapp", "unregistered_pager", "pagerduty"]
    print(f"  Attempting broadcast to: {batch_channels}")
    batch_results = service.dispatch(broadcast_notif, batch_channels)

    for r in batch_results:
        symbol = "[SUCCESS]" if r.success else "[FAILED]"
        print(f"  Channel [{r.channel:18}] -> {symbol} | {r.message}")

    # 6. Demonstrating Input Validation
    print("\n" + "-" * 72)
    print("[Step 6] Demonstrating Channel Recipient Validation Failure...")
    malformed_email_notif = Notification(
        recipient="not_an_email_address",
        subject="Test Validation",
        body="This recipient should fail validation gracefully.",
    )
    fail_result = service.send(malformed_email_notif, "email")
    print(f"  Channel: email | Target: '{malformed_email_notif.recipient}'")
    print(f"  Success: {fail_result.success}")
    print(f"  Message: {fail_result.message}")
    print(f"  Details: {fail_result.error_details}")

    # 7. Demonstrating Unsupported Channel Exception
    print("\n" + "-" * 72)
    print("[Step 7] Demonstrating Direct UnsupportedChannelError Exception Handling...")
    try:
        service.send(broadcast_notif, "discord")
    except UnsupportedChannelError as exc:
        print(f"  [OK] Caught expected UnsupportedChannelError: {exc}")

    print("\n" + "=" * 72)
    print(" DEMO COMPLETED SUCCESSFULLY -- 100% OFFLINE (NO EXTERNAL NETWORK CALLS)")
    print("=" * 72)


if __name__ == "__main__":
    main()

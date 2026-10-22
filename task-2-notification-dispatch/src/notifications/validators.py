"""
validators.py — Pure validation functions with no side effects.

Each function accepts a string and returns a boolean indicating validity.
No exceptions are raised; callers decide what to do with invalid input.
"""

from __future__ import annotations

import re


def validate_email(address: str) -> bool:
    """
    Validate an email address using a basic regex.

    Requirements: must contain '@', a local part, a domain name, and a dot
    in the domain portion.

    Parameters
    ----------
    address : str
        The email address to validate.

    Returns
    -------
    bool
        True if the address matches the basic email pattern.
    """
    if not isinstance(address, str):
        return False
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(pattern, address.strip()))


def validate_phone(number: str) -> bool:
    """
    Validate a phone number in E.164-ish format.

    Requirements: optional leading '+', followed by 7–15 digits only.

    Parameters
    ----------
    number : str
        The phone number string to validate.

    Returns
    -------
    bool
        True if the number matches the expected pattern.
    """
    if not isinstance(number, str):
        return False
    pattern = r"^\+?\d{7,15}$"
    return bool(re.match(pattern, number.strip()))


def validate_slack_channel(channel: str) -> bool:
    """
    Validate a Slack channel or user destination.

    Requirements: must start with '#' (channel) or '@' (user), and have
    at least one additional non-whitespace character.

    Parameters
    ----------
    channel : str
        The Slack destination string to validate.

    Returns
    -------
    bool
        True if the channel/user string is valid.
    """
    if not isinstance(channel, str):
        return False
    stripped = channel.strip()
    if len(stripped) < 2:
        return False
    if not (stripped.startswith("#") or stripped.startswith("@")):
        return False
    # Ensure there is content after the prefix
    return len(stripped[1:].strip()) > 0


def validate_whatsapp_number(number: str) -> bool:
    """
    Validate a WhatsApp-compatible phone number.

    Uses the same E.164-ish format as validate_phone: optional '+',
    followed by 7–15 digits. WhatsApp requires internationally formatted
    numbers.

    Parameters
    ----------
    number : str
        The WhatsApp number string to validate.

    Returns
    -------
    bool
        True if the number is a valid WhatsApp number.
    """
    return validate_phone(number)

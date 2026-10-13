"""Phone numbers in one international format (04 §0), Romania by default (auth-layer §3.5)."""

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType

# Staff sign in by SMS, so their numbers must be able to receive one (auth-layer AL12).
SMS_TYPES = {PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE}


def normalize(raw: str) -> str:
    """E.164 for a number as typed or as Firebase reports it; ValueError if not valid."""
    try:
        number = phonenumbers.parse(raw, "RO")
    except NumberParseException:
        raise ValueError("not a phone number") from None
    if not phonenumbers.is_valid_number(number):
        raise ValueError("not a valid phone number")
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)


def is_mobile(e164: str) -> bool:
    return phonenumbers.number_type(phonenumbers.parse(e164)) in SMS_TYPES


def mask(e164: str) -> str:
    """A number as it may appear in logs (auth-layer AL15): +40700***009."""
    return f"{e164[:6]}***{e164[-3:]}"

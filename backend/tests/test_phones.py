import pytest

from app.core.phones import is_mobile, mask, normalize


@pytest.mark.parametrize(
    ("raw", "e164"),
    [
        ("0722 123 456", "+40722123456"),
        ("+40722123456", "+40722123456"),
        ("0040 722 123 456", "+40722123456"),
        ("(0722) 123-456", "+40722123456"),
        ("0700 000 002", "+40700000002"),  # a Firebase test number (auth-layer §5)
        ("0256 123 456", "+40256123456"),  # Timișoara landline
        ("+16505550101", "+16505550101"),
    ],
)
def test_normalize(raw, e164):
    assert normalize(raw) == e164


@pytest.mark.parametrize("raw", ["12345", "", "not a number", "+40 1"])
def test_normalize_refuses(raw):
    with pytest.raises(ValueError):
        normalize(raw)


def test_is_mobile():
    assert is_mobile("+40722123456")
    assert is_mobile("+40700000001")
    assert is_mobile("+16505550101")  # FIXED_LINE_OR_MOBILE: can receive an SMS
    assert not is_mobile("+40256123456")


def test_mask():
    assert mask("+40700000009") == "+40700***009"

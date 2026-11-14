"""Approximate senior locations from a fixed street table (design 2026-11-14 §7)."""

import math
import uuid

import pytest

from app.seniors.places import approx_location

SEED_STREETS = [
    "Bulevardul Cetății",
    "Bulevardul Eroilor de la Tisa",
    "Bulevardul Take Ionescu",
    "Calea Aradului",
    "Calea Buziașului",
    "Calea Girocului",
    "Calea Lipovei",
    "Calea Martirilor",
    "Calea Șagului",
    "Strada Alba Iulia",
    "Strada Arieș",
    "Strada Bucovinei",
    "Strada Cluj",
    "Strada Gheorghe Lazăr",
    "Strada Lipovei",
    "Strada Memorandumului",
    "Strada Mărășești",
    "Strada Pestalozzi",
    "Strada Take Ionescu",
]
SENIOR = uuid.UUID("01a1dab6-dc6e-70aa-a0dc-9acea72bc108")


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    dlat = (a[0] - b[0]) * 111_320
    dlng = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlng)


@pytest.mark.parametrize("street", SEED_STREETS)
def test_a_seed_street_resolves(street):
    point = approx_location(SENIOR, street)

    assert point is not None
    lat, lng = point
    assert 45.70 <= lat <= 45.81 and 21.15 <= lng <= 21.30


@pytest.mark.parametrize(
    "variants",
    [
        ["calea aradului", "Calea Aradului", "Aradului"],
        ["Str. Mărășești", "Marasesti", "Strada Mărășești"],
    ],
)
def test_spelling_variants_match(variants):
    points = [approx_location(SENIOR, v) for v in variants]

    assert all(p is not None for p in points)
    assert all(metres(points[0], p) < 100 for p in points)


@pytest.mark.parametrize("street", ["Strada Inexistentă", None, ""])
def test_unknown_street_is_none(street):
    assert approx_location(SENIOR, street) is None


def test_neighbours_do_not_stack():
    a = approx_location(uuid.uuid4(), "Calea Aradului")
    b = approx_location(uuid.uuid4(), "Calea Aradului")
    base = approx_location(uuid.UUID(int=0), "Calea Aradului")

    assert a != b
    assert metres(a, base) < 120 and metres(b, base) < 120

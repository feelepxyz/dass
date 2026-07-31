"""Assertion helpers shared across the suite."""

import pytest


def almost(expected: float, places: int = 7) -> object:
    """`assertAlmostEqual`'s bar, as a comparand for a bare `assert`.

    `assertAlmostEqual` rounds the difference to `places` decimals, so it holds
    the two values within an *absolute* 0.5e-places. `pytest.approx` defaults to
    a *relative* 1e-6, which on mm-scale geometry in the hundreds is three
    orders of magnitude looser. Giving `approx` an absolute tolerance and no
    relative one makes it purely absolute, which is the comparison the geometry
    assertions were written against.
    """
    return pytest.approx(expected, abs=0.5 * 10.0**-places)

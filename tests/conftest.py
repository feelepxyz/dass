"""Fixtures shared across the suite.

`build` runs the whole CadQuery model, so the default assembly is built once for
the session and shared. Nothing in the suite writes to it.
"""

import pytest

from dass import Design, Part, build
from dass.cutlists import CutPiece, beam_pieces, cladding_pieces


@pytest.fixture(scope="session")
def design() -> Design:
    return Design()


@pytest.fixture(scope="session")
def parts(design: Design) -> list[Part]:
    return build(design)[1]


@pytest.fixture(scope="session")
def by_name(parts: list[Part]) -> dict[str, Part]:
    return {part.name: part for part in parts}


@pytest.fixture(scope="session")
def beams(design: Design) -> list[CutPiece]:
    return beam_pieces(design)


@pytest.fixture(scope="session")
def boards(design: Design) -> list[CutPiece]:
    return cladding_pieces(design)

import importlib

import pytest

import pokerbot

SUBPACKAGES = [
    "pokerbot.engine",
    "pokerbot.eval",
    "pokerbot.agents",
    "pokerbot.agents.heuristic",
    "pokerbot.agents.gto",
    "pokerbot.agents.modeling",
    "pokerbot.agents.personality",
    "pokerbot.arena",
    "pokerbot.api",
    "pokerbot.persistence",
    "pokerbot.cli",
    "pokerbot.domain",
    "pokerbot.agents.base",
]


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports(name: str) -> None:
    importlib.import_module(name)


def test_version_is_exposed() -> None:
    assert isinstance(pokerbot.__version__, str)
    assert pokerbot.__version__

"""Regression coverage for #138516."""

from typing import get_type_hints

from tui_gateway import methods_onboarding


def test_shared_nous_store_annotation_resolves_from_its_module() -> None:
    """The split handler must import under eager-annotation Python versions."""
    assert "return" in get_type_hints(methods_onboarding._shared_nous_store)

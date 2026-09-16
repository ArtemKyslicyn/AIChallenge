"""Unit tests for Day-12 personalization + owner keys."""

from __future__ import annotations

from uuid import uuid4

from app.domain.owner_key import memory_owner_key
from app.domain.personalization import (
    PreferenceProfile,
    build_personalization_extra,
    format_preference_block,
    get_expert_lens,
)


def test_owner_key_visitor_vs_user() -> None:
    vid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert memory_owner_key(visitor_id=vid, user_id=None) == vid
    uid = uuid4()
    assert memory_owner_key(visitor_id=vid, user_id=uid) == f"user:{uid}"


def test_preference_and_lens_blocks_order() -> None:
    pref = PreferenceProfile(
        id=uuid4(),
        owner_key="v",
        name="Кратко · JSON",
        style="кратко",
        format="JSON",
        constraints="без воды",
    )
    lens = get_expert_lens("economist")
    extra = build_personalization_extra(preference=pref, lens=lens)
    assert "предпочтения" in extra
    assert "Экономист" in extra
    assert extra.index("предпочтения") < extra.index("Экономист")
    assert format_preference_block(None) == ""
    assert get_expert_lens("neutral").system_addendum == ""

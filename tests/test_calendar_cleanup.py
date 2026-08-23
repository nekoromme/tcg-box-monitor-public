from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from tcg_monitor.cli import (
    _cleanup_confirmed_false_positive_cases,
    _cleanup_confirmed_false_positive_releases,
)
from tcg_monitor.google_calendar import CalendarAdapter
from tcg_monitor.state import MonitorState

KOJIMA_CASE_ID = "b3ead67cf50edb332b84384beb3bfc8c708c5eb0601e5cf95895b5f1def6043a"
DMM_CASE_ID = "2b4300ef9195694ee76e2b2e80acd2c73fca9b2ca63ebefd3ef41484542cc98e"
KOJIMA_EVENT_ID = "tcg8c2393b32768f27eb41c378f08ad328d2c788c4c60a29f8853489510de004"
DMM_EVENT_ID = "tcg870cbc59d0b2aed2b3be8a58ab631f45e32a2135492b9706fad040139dd7f"
FALSE_RELEASE_ID = "ec5c020af436d8a7cd994917b711a1094f837829544aea5bb12241fc7aa400c0"
FALSE_RELEASE_EVENT_ID = "tcg7bef96ffbc518ca8b8953882e69ad1b2b2f2ef2c7a0d63862360748037d42"
WORLD_DUPLICATE_ID = "c06ffae922311fab6aebd0bc5df2ea5ea070328f3362276030949913e34d6aba"
WORLD_DUPLICATE_EVENT_ID = "tcged9d1a1cdaeec6893c0456f1fbfafae75c99288d564efc75491b2b6c9eab8"
WORLD_STATE_ONLY_ID = "71ddfbc10aa3cb757dffcd0660c9ebc9714b451e02b5ac129582107e30ae82fe"
CELEBRATION_DUPLICATE_ID = "4955064739124218e139bef66f488874f123ce078fd7fabbb508eae04eebc6ad"
CELEBRATION_DUPLICATE_EVENT_ID = "tcg02ea64042327c86f85fbcb1d498277fcfcefc32e61e86dee1a63feb970551"
FUTURISTIC_RELEASE_ID = "49550fefef3af3302da3d20b912608762c58ab036d4dbd3fff229b86820d295e"
HOBBY_SEARCH_SOCIAL_CASE_ID = "2b5488f0479147ce1524d884875042da1e84ec46cf773a9ddc156f211642cd02"
HOBBY_SEARCH_SOCIAL_EVENT_ID = "tcg2193158b6acc1392576fb442a616c9d5ad04ed7287fdc27e8e4883e9e43d4"


class _Request:
    def __init__(self, value: object = None) -> None:
        self.value = value

    def execute(self) -> object:
        return self.value


class _Events:
    def __init__(self, event: dict[str, Any]) -> None:
        self.event = event
        self.get_calls: list[dict[str, str]] = []
        self.delete_calls: list[dict[str, str]] = []

    def get(self, **kwargs: str) -> _Request:
        self.get_calls.append(kwargs)
        return _Request(self.event)

    def delete(self, **kwargs: str) -> _Request:
        self.delete_calls.append(kwargs)
        return _Request()


class _Service:
    def __init__(self, events: _Events) -> None:
        self.events_resource = events

    def events(self) -> _Events:
        return self.events_resource


def test_delete_owned_event_verifies_private_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    events = _Events(
        {
            "summary": "【ポケカ抽選開始】コジマ／ストームエメラルダ",
            "extendedProperties": {
                "private": {
                    "kind": "lottery",
                    "internal_id": KOJIMA_CASE_ID,
                }
            },
        }
    )
    adapter = CalendarAdapter(calendar_id="calendar@example.com")
    adapter._service = _Service(events)

    result = adapter.delete_owned_event(
        KOJIMA_EVENT_ID,
        kind="lottery",
        internal_id=KOJIMA_CASE_ID,
    )

    assert result["status"] == "deleted"
    assert result["summary"] == "【ポケカ抽選開始】コジマ／ストームエメラルダ"
    assert events.get_calls == [{"calendarId": "calendar@example.com", "eventId": KOJIMA_EVENT_ID}]
    assert events.delete_calls == [
        {"calendarId": "calendar@example.com", "eventId": KOJIMA_EVENT_ID}
    ]


def test_delete_owned_event_refuses_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    events = _Events(
        {
            "summary": "別の予定",
            "extendedProperties": {
                "private": {
                    "kind": "lottery",
                    "internal_id": "different-case",
                }
            },
        }
    )
    adapter = CalendarAdapter(calendar_id="calendar@example.com")
    adapter._service = _Service(events)

    with pytest.raises(RuntimeError, match="識別情報と一致しません"):
        adapter.delete_owned_event(
            KOJIMA_EVENT_ID,
            kind="lottery",
            internal_id=KOJIMA_CASE_ID,
        )

    assert not events.delete_calls


def _false_positive_state(path: Path) -> MonitorState:
    state = MonitorState.load(path)
    state.data["seen_cases"] = {
        KOJIMA_CASE_ID: {
            "retailer_id": "kojima",
            "retailer_name": "コジマ",
            "product_name": "ストームエメラルダ",
            "start_at": "2026-07-30",
            "source_url": "https://x.com/gamegetnavi/status/2080645250255827125",
        },
        DMM_CASE_ID: {
            "retailer_id": "dmm_myca",
            "retailer_name": "DMMマイカ",
            "product_name": "本日以降",
            "start_at": "2026-07-30",
            "source_url": "https://x.com/DMM_Myca/status/2082586970123866217",
        },
    }
    state.data["calendar_sync"] = {
        f"lottery:{KOJIMA_CASE_ID}": {"event_id": KOJIMA_EVENT_ID},
        f"lottery:{DMM_CASE_ID}": {"event_id": DMM_EVENT_ID},
    }
    state.data["delivery_journal"] = {
        f"lottery:started:{KOJIMA_CASE_ID}": {"status": "complete"},
        f"lottery:started:{DMM_CASE_ID}": {"status": "complete"},
    }
    return state


def test_cleanup_removes_only_confirmed_false_positive_state(tmp_path: Path) -> None:
    state = _false_positive_state(tmp_path / "monitor_state.json")
    state.data["seen_cases"]["keep"] = {"retailer_id": "other"}
    state.data["calendar_sync"]["lottery:keep"] = {"event_id": "tcgkeep"}
    state.data["delivery_journal"]["lottery:started:keep"] = {"status": "complete"}
    calendar = MagicMock(spec=CalendarAdapter)
    calendar.delete_owned_event.side_effect = [
        {"status": "deleted", "event_id": KOJIMA_EVENT_ID},
        {"status": "deleted", "event_id": DMM_EVENT_ID},
    ]

    results = _cleanup_confirmed_false_positive_cases(state, calendar)

    assert [result["retailer"] for result in results] == ["コジマ", "DMMマイカ"]
    assert calendar.delete_owned_event.call_args_list == [
        call(KOJIMA_EVENT_ID, kind="lottery", internal_id=KOJIMA_CASE_ID),
        call(DMM_EVENT_ID, kind="lottery", internal_id=DMM_CASE_ID),
    ]
    for case_id in (KOJIMA_CASE_ID, DMM_CASE_ID):
        assert case_id not in state.data["seen_cases"]
        assert f"lottery:{case_id}" not in state.data["calendar_sync"]
        assert f"lottery:started:{case_id}" not in state.data["delivery_journal"]
    assert "keep" in state.data["seen_cases"]
    assert "lottery:keep" in state.data["calendar_sync"]
    assert "lottery:started:keep" in state.data["delivery_journal"]

    reloaded = MonitorState.load(state.path)
    assert KOJIMA_CASE_ID not in reloaded.data["seen_cases"]
    assert DMM_CASE_ID not in reloaded.data["seen_cases"]

    assert _cleanup_confirmed_false_positive_cases(state, calendar) == []
    assert calendar.delete_owned_event.call_count == 2


def test_cleanup_stops_before_delete_when_state_does_not_match(tmp_path: Path) -> None:
    state = _false_positive_state(tmp_path / "monitor_state.json")
    state.data["seen_cases"][KOJIMA_CASE_ID]["product_name"] = "別の商品"
    calendar = MagicMock(spec=CalendarAdapter)

    with pytest.raises(RuntimeError, match="確認済み記録と一致しません"):
        _cleanup_confirmed_false_positive_cases(state, calendar)

    calendar.delete_owned_event.assert_not_called()
    assert KOJIMA_CASE_ID in state.data["seen_cases"]


def test_cleanup_removes_superseded_hobby_search_social_event(
    tmp_path: Path,
) -> None:
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["seen_cases"] = {
        HOBBY_SEARCH_SOCIAL_CASE_ID: {
            "retailer_id": "hobby_search",
            "retailer_name": "ホビーサーチ",
            "product_name": "拡張パック「ストームエメラルダ」",
            "start_at": "2026-08-12",
            "source_url": ("https://x.com/PokeGetInfoMain/status/2087464419907572128"),
        },
        "trusted-exact-case": {
            "retailer_id": "hobby_search",
            "retailer_name": "ホビーサーチ",
            "product_name": "拡張パック「ストームエメラルダ」",
            "start_at": "2026-08-12 18:00:00+09:00",
            "source_url": "https://snkrdunk.com/articles/32892/",
        },
    }
    state.data["calendar_sync"] = {
        f"lottery:{HOBBY_SEARCH_SOCIAL_CASE_ID}": {"event_id": HOBBY_SEARCH_SOCIAL_EVENT_ID},
        "lottery:trusted-exact-case": {"event_id": "tcgtrusted"},
    }
    state.data["delivery_journal"] = {
        f"lottery:started:{HOBBY_SEARCH_SOCIAL_CASE_ID}": {"status": "complete"},
        "lottery:started:trusted-exact-case": {"status": "complete"},
    }
    calendar = MagicMock(spec=CalendarAdapter)
    calendar.delete_owned_event.return_value = {
        "status": "deleted",
        "event_id": HOBBY_SEARCH_SOCIAL_EVENT_ID,
    }

    results = _cleanup_confirmed_false_positive_cases(state, calendar)

    assert results == [
        {
            "retailer": "ホビーサーチ",
            "product": "拡張パック「ストームエメラルダ」",
            "status": "deleted",
        }
    ]
    calendar.delete_owned_event.assert_called_once_with(
        HOBBY_SEARCH_SOCIAL_EVENT_ID,
        kind="lottery",
        internal_id=HOBBY_SEARCH_SOCIAL_CASE_ID,
    )
    assert HOBBY_SEARCH_SOCIAL_CASE_ID not in state.data["seen_cases"]
    assert "trusted-exact-case" in state.data["seen_cases"]


def test_cleanup_removes_only_confirmed_false_snkrdunk_release(tmp_path: Path) -> None:
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["seen_releases"] = {
        FALSE_RELEASE_ID: {
            "game_id": "pokemon_card",
            "product_name": "ハイクラスパック「ポケットモンスター ルビー・サファイア」",
            "release_date": "2026-07-31",
            "source_url": "https://snkrdunk.com/articles/32581/",
        },
        "keep": {"game_id": "pokemon_card"},
    }
    state.data["calendar_sync"] = {
        f"release:{FALSE_RELEASE_ID}": {"event_id": FALSE_RELEASE_EVENT_ID},
        "release:keep": {"event_id": "tcgkeep"},
    }
    state.data["delivery_journal"] = {
        f"release:{FALSE_RELEASE_ID}": {"status": "complete"},
        "release:keep": {"status": "complete"},
    }
    calendar = MagicMock(spec=CalendarAdapter)
    calendar.delete_owned_event.return_value = {
        "status": "deleted",
        "event_id": FALSE_RELEASE_EVENT_ID,
    }

    results = _cleanup_confirmed_false_positive_releases(state, calendar)

    assert results == [
        {
            "product": "ハイクラスパック「ポケットモンスター ルビー・サファイア」",
            "status": "deleted",
        }
    ]
    calendar.delete_owned_event.assert_called_once_with(
        FALSE_RELEASE_EVENT_ID,
        kind="release",
        internal_id=FALSE_RELEASE_ID,
    )
    assert FALSE_RELEASE_ID not in state.data["seen_releases"]
    assert f"release:{FALSE_RELEASE_ID}" not in state.data["calendar_sync"]
    assert f"release:{FALSE_RELEASE_ID}" not in state.data["delivery_journal"]
    assert "keep" in state.data["seen_releases"]
    assert _cleanup_confirmed_false_positive_releases(state, calendar) == []


def test_cleanup_removes_confirmed_historical_duplicate_releases(
    tmp_path: Path,
) -> None:
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["seen_releases"] = {
        WORLD_DUPLICATE_ID: {
            "game_id": "one_piece_card",
            "product_name": "ブースターパック「世界最強の戦士」",
            "release_date": "2026-08-22",
            "source_url": "https://snkrdunk.com/articles/32599/",
        },
        WORLD_STATE_ONLY_ID: {
            "game_id": "one_piece_card",
            "product_name": "8月22日 ブースターパック「世界最強の戦士」",
            "release_date": "2026-08-22",
            "source_url": "https://snkrdunk.com/articles/14006/",
        },
        CELEBRATION_DUPLICATE_ID: {
            "game_id": "pokemon_card",
            "product_name": "拡張パック「30th CELEBRATION」",
            "release_date": "2026-09-16",
            "source_url": "https://www.pokemon-card.com/products/",
        },
    }
    state.data["calendar_sync"] = {
        f"release:{WORLD_DUPLICATE_ID}": {"event_id": WORLD_DUPLICATE_EVENT_ID},
        f"release:{CELEBRATION_DUPLICATE_ID}": {"event_id": CELEBRATION_DUPLICATE_EVENT_ID},
    }
    state.data["delivery_journal"] = {
        f"release:{WORLD_DUPLICATE_ID}": {"status": "complete"},
        f"release:{WORLD_STATE_ONLY_ID}": {"status": "complete"},
        f"release:{CELEBRATION_DUPLICATE_ID}": {"status": "complete"},
    }
    calendar = MagicMock(spec=CalendarAdapter)
    calendar.delete_owned_event.side_effect = [
        {"status": "deleted", "event_id": WORLD_DUPLICATE_EVENT_ID},
        {"status": "deleted", "event_id": CELEBRATION_DUPLICATE_EVENT_ID},
    ]

    results = _cleanup_confirmed_false_positive_releases(state, calendar)

    assert results == [
        {
            "product": "ブースターパック「世界最強の戦士」",
            "status": "deleted",
        },
        {
            "product": "8月22日 ブースターパック「世界最強の戦士」",
            "status": "state_only",
        },
        {
            "product": "拡張パック「30th CELEBRATION」",
            "status": "deleted",
        },
    ]
    assert calendar.delete_owned_event.call_args_list == [
        call(
            WORLD_DUPLICATE_EVENT_ID,
            kind="release",
            internal_id=WORLD_DUPLICATE_ID,
        ),
        call(
            CELEBRATION_DUPLICATE_EVENT_ID,
            kind="release",
            internal_id=CELEBRATION_DUPLICATE_ID,
        ),
    ]
    for release_id in (
        WORLD_DUPLICATE_ID,
        WORLD_STATE_ONLY_ID,
        CELEBRATION_DUPLICATE_ID,
    ):
        assert release_id not in state.data["seen_releases"]
        assert f"release:{release_id}" not in state.data["calendar_sync"]
        assert f"release:{release_id}" not in state.data["delivery_journal"]


def test_cleanup_removes_misclassified_pokemon_other_product(tmp_path: Path) -> None:
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["seen_releases"] = {
        FUTURISTIC_RELEASE_ID: {
            "game_id": "pokemon_card",
            "product_name": "その他の商品 「30th CELEBRATION FUTURISTIC BOX」",
            "release_date": "2026-09-16",
            "source_url": "https://www.pokemon-card.com/products/",
        },
        "keep": {
            "game_id": "pokemon_card",
            "product_name": "拡張パック「30th CELEBRATION」",
            "release_date": "2026-09-16",
            "source_url": "https://www.pokemon-card.com/products/",
        },
    }
    state.data["calendar_sync"] = {
        f"release:{FUTURISTIC_RELEASE_ID}": {"event_id": CELEBRATION_DUPLICATE_EVENT_ID},
        "release:keep": {"event_id": "tcgkeep"},
    }
    state.data["delivery_journal"] = {
        f"release:{FUTURISTIC_RELEASE_ID}": {"status": "complete"},
        "release:keep": {"status": "complete"},
    }
    calendar = MagicMock(spec=CalendarAdapter)
    calendar.delete_owned_event.return_value = {
        "status": "deleted",
        "event_id": CELEBRATION_DUPLICATE_EVENT_ID,
    }

    results = _cleanup_confirmed_false_positive_releases(state, calendar)

    assert results == [
        {
            "product": "その他の商品 「30th CELEBRATION FUTURISTIC BOX」",
            "status": "deleted",
        }
    ]
    calendar.delete_owned_event.assert_called_once_with(
        CELEBRATION_DUPLICATE_EVENT_ID,
        kind="release",
        internal_id=FUTURISTIC_RELEASE_ID,
    )
    assert FUTURISTIC_RELEASE_ID not in state.data["seen_releases"]
    assert "keep" in state.data["seen_releases"]

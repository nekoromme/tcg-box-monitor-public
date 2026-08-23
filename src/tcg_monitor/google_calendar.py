from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Any

# Google Calendarのイベント色「Tomato」。公式例でも赤背景として使われるID。
RELEASE_EVENT_COLOR_ID = "11"


def normalize_calendar_id(value: str | None) -> str:
    """Remove accidental whitespace introduced while copying a Calendar ID."""
    return (value or "").strip()


@dataclass
class CalendarAdapter:
    calendar_id: str | None = None
    dry_run: bool = False
    _service: Any = field(default=None, init=False, repr=False)

    def _service_client(self) -> Any:
        if self._service is not None:
            return self._service
        credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not credentials_json:
            raise RuntimeError(
                "Google CalendarのSecretsが不足しています: "
                "GOOGLE_SERVICE_ACCOUNT_JSON と GOOGLE_CALENDAR_ID を確認してください"
            )
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
            json.loads(credentials_json),
            # カレンダー本体や共有設定を変更できる広い権限は不要。
            # このツールが使う「予定の読取・作成・更新・削除」だけに絞る。
            scopes=["https://www.googleapis.com/auth/calendar.events"],
        )
        self._service = build(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
        return self._service

    def event_id(self, kind: str, internal_id: str) -> str:
        return ("tcg" + sha256(f"{kind}:{internal_id}".encode()).hexdigest())[:64]

    def _event_body(
        self,
        event_id: str,
        kind: str,
        internal_id: str,
        summary: str,
        when: datetime | date,
        description: str,
        dedupe_key: str | None,
    ) -> dict[str, object]:
        private_properties = {"internal_id": internal_id, "kind": kind}
        if dedupe_key:
            private_properties["dedupe_key"] = dedupe_key
        body: dict[str, object] = {
            "id": event_id,
            "summary": summary,
            "description": description,
            "extendedProperties": {"private": private_properties},
        }
        if kind == "release":
            body["colorId"] = RELEASE_EVENT_COLOR_ID
        if isinstance(when, datetime):
            body.update(
                {
                    "start": {"dateTime": when.isoformat()},
                    "end": {"dateTime": (when + timedelta(minutes=15)).isoformat()},
                }
            )
        else:
            body.update(
                {
                    "start": {"date": when.isoformat()},
                    "end": {"date": (when + timedelta(days=1)).isoformat()},
                }
            )
        return body

    def _calendar_id(self) -> str:
        calendar_id = normalize_calendar_id(
            self.calendar_id or os.getenv("GOOGLE_CALENDAR_ID")
        )
        if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or not calendar_id:
            raise RuntimeError(
                "Google CalendarのSecretsが不足しています: "
                "GOOGLE_SERVICE_ACCOUNT_JSON と GOOGLE_CALENDAR_ID を確認してください"
            )
        return calendar_id

    @staticmethod
    def _owned_event_matches(
        event: object,
        body: dict[str, object],
        *,
        kind: str,
        internal_id: str,
    ) -> bool:
        if not isinstance(event, dict):
            return False
        private = event.get("extendedProperties", {}).get("private", {})
        if not isinstance(private, dict) or (
            private.get("kind") != kind
            or private.get("internal_id") != internal_id
        ):
            raise RuntimeError(
                "Google Calendar予定が監視状態の識別情報と一致しません"
            )
        return all(event.get(field) == body.get(field) for field in body if field != "id")

    def upsert(
        self,
        kind: str,
        internal_id: str,
        summary: str,
        when: datetime | date,
        description: str,
        dedupe_key: str | None = None,
    ) -> dict[str, str]:
        event_id = self.event_id(kind, internal_id)
        body = self._event_body(
            event_id,
            kind,
            internal_id,
            summary,
            when,
            description,
            dedupe_key,
        )
        if self.dry_run:
            return {"status": "dry_run", "event_id": event_id}

        calendar_id = self._calendar_id()

        from googleapiclient.errors import HttpError

        service = self._service_client()
        status = "inserted"
        try:
            service.events().insert(calendarId=calendar_id, body=body).execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                raise RuntimeError(
                    "Google Calendarが見つかりません。GOOGLE_CALENDAR_IDが正しいことと、"
                    "対象カレンダーをサービスアカウントへ『予定の変更』権限で"
                    "共有していることを確認してください"
                ) from exc
            if exc.resp.status != 409:
                raise RuntimeError(
                    f"Google Calendar APIエラー: status={exc.resp.status}"
                ) from None
            service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=body,
            ).execute()
            status = "updated"

        return {"status": status, "event_id": event_id}

    def reconcile(
        self,
        kind: str,
        internal_id: str,
        summary: str,
        when: datetime | date,
        description: str,
        dedupe_key: str | None = None,
        known_event_id: str | None = None,
    ) -> dict[str, str]:
        """Ensure that one monitor-owned event actually exists and is current.

        The state file is only a hint. A user can delete an event, change the
        target calendar, or leave a tombstoned deterministic ID behind. Search
        by private identity before recreating so those cases heal without
        producing a duplicate.
        """

        deterministic_id = self.event_id(kind, internal_id)
        event_id = (known_event_id or deterministic_id).strip() or deterministic_id
        body = self._event_body(
            event_id,
            kind,
            internal_id,
            summary,
            when,
            description,
            dedupe_key,
        )
        if self.dry_run:
            return {"status": "dry_run", "event_id": event_id}

        calendar_id = self._calendar_id()
        from googleapiclient.errors import HttpError

        service = self._service_client()
        event: dict[str, object] | None = None
        try:
            raw_event = (
                service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
            event = raw_event if isinstance(raw_event, dict) else None
        except HttpError as exc:
            if exc.resp.status not in {404, 410}:
                raise RuntimeError(
                    f"Google Calendar APIエラー: status={exc.resp.status}"
                ) from None

        if event is None:
            try:
                result = (
                    service.events()
                    .list(
                        calendarId=calendar_id,
                        privateExtendedProperty=[
                            f"kind={kind}",
                            f"internal_id={internal_id}",
                        ],
                        showDeleted=False,
                        maxResults=10,
                    )
                    .execute()
                )
            except HttpError as exc:
                if exc.resp.status == 404:
                    raise RuntimeError(
                        "Google Calendarが見つかりません。GOOGLE_CALENDAR_IDが正しいことと、"
                        "対象カレンダーをサービスアカウントへ『予定の変更』権限で"
                        "共有していることを確認してください"
                    ) from exc
                raise RuntimeError(
                    f"Google Calendar APIエラー: status={exc.resp.status}"
                ) from None
            items = result.get("items", []) if isinstance(result, dict) else []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                private = item.get("extendedProperties", {}).get("private", {})
                if not isinstance(private, dict) or (
                    private.get("kind") != kind
                    or private.get("internal_id") != internal_id
                ):
                    continue
                candidate_id = str(item.get("id") or "")
                if candidate_id:
                    event_id = candidate_id
                    body["id"] = event_id
                    event = item
                    break

        if event is not None:
            if self._owned_event_matches(
                event,
                body,
                kind=kind,
                internal_id=internal_id,
            ):
                return {"status": "unchanged", "event_id": event_id}
            try:
                service.events().update(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=body,
                ).execute()
            except HttpError as exc:
                raise RuntimeError(
                    f"Google Calendar APIエラー: status={exc.resp.status}"
                ) from None
            return {"status": "updated", "event_id": event_id}

        body["id"] = deterministic_id
        try:
            service.events().insert(calendarId=calendar_id, body=body).execute()
            return {"status": "inserted", "event_id": deterministic_id}
        except HttpError as exc:
            if exc.resp.status not in {409, 410}:
                raise RuntimeError(
                    f"Google Calendar APIエラー: status={exc.resp.status}"
                ) from None

        # Google keeps deleted IDs as tombstones, so a deterministic ID cannot
        # always be reused. The returned recovery ID becomes the durable state
        # hint on the next run; the private-property search prevents duplicates.
        recovery_id = (
            "tcg"
            + sha256(
                f"{kind}:{internal_id}:{datetime.now().isoformat()}".encode()
            ).hexdigest()
        )[:64]
        body["id"] = recovery_id
        try:
            service.events().insert(calendarId=calendar_id, body=body).execute()
        except HttpError as exc:
            raise RuntimeError(
                f"Google Calendar APIエラー: status={exc.resp.status}"
            ) from None
        return {"status": "inserted", "event_id": recovery_id}

    def set_owned_event_color(
        self,
        event_id: str,
        *,
        kind: str,
        internal_id: str,
        color_id: str,
    ) -> dict[str, str]:
        """Change only the color after verifying that the monitor owns the event."""

        if self.dry_run:
            return {"status": "dry_run", "event_id": event_id}

        calendar_id = normalize_calendar_id(
            self.calendar_id or os.getenv("GOOGLE_CALENDAR_ID")
        )
        if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or not calendar_id:
            raise RuntimeError(
                "Google CalendarのSecretsが不足しています: "
                "GOOGLE_SERVICE_ACCOUNT_JSON と GOOGLE_CALENDAR_ID を確認してください"
            )

        from googleapiclient.errors import HttpError

        service = self._service_client()
        try:
            event = (
                service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status in {404, 410}:
                return {"status": "not_found", "event_id": event_id}
            raise RuntimeError(
                f"Google Calendar APIエラー: status={exc.resp.status}"
            ) from None

        private = (
            event.get("extendedProperties", {}).get("private", {})
            if isinstance(event, dict)
            else {}
        )
        if private.get("kind") != kind or private.get("internal_id") != internal_id:
            raise RuntimeError(
                "色変更対象のGoogle Calendar予定が監視状態の識別情報と一致しません"
            )

        try:
            service.events().patch(
                calendarId=calendar_id,
                eventId=event_id,
                body={"colorId": color_id},
            ).execute()
        except HttpError as exc:
            if exc.resp.status in {404, 410}:
                return {"status": "not_found", "event_id": event_id}
            raise RuntimeError(
                f"Google Calendar APIエラー: status={exc.resp.status}"
            ) from None
        return {
            "status": "updated",
            "event_id": event_id,
            "color_id": color_id,
        }

    def delete_owned_event(
        self,
        event_id: str,
        *,
        kind: str,
        internal_id: str,
    ) -> dict[str, str]:
        """Delete one monitor-owned event after verifying its private identity."""

        if self.dry_run:
            return {"status": "dry_run", "event_id": event_id}

        calendar_id = normalize_calendar_id(
            self.calendar_id or os.getenv("GOOGLE_CALENDAR_ID")
        )
        if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or not calendar_id:
            raise RuntimeError(
                "Google CalendarのSecretsが不足しています: "
                "GOOGLE_SERVICE_ACCOUNT_JSON と GOOGLE_CALENDAR_ID を確認してください"
            )

        from googleapiclient.errors import HttpError

        service = self._service_client()
        try:
            event = (
                service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status in {404, 410}:
                return {"status": "not_found", "event_id": event_id}
            raise RuntimeError(
                f"Google Calendar APIエラー: status={exc.resp.status}"
            ) from None

        private = (
            event.get("extendedProperties", {}).get("private", {})
            if isinstance(event, dict)
            else {}
        )
        if private.get("kind") != kind or private.get("internal_id") != internal_id:
            raise RuntimeError(
                "削除対象のGoogle Calendar予定が監視状態の識別情報と一致しません"
            )

        try:
            service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()
        except HttpError as exc:
            if exc.resp.status not in {404, 410}:
                raise RuntimeError(
                    f"Google Calendar APIエラー: status={exc.resp.status}"
                ) from None
            return {"status": "not_found", "event_id": event_id}
        return {
            "status": "deleted",
            "event_id": event_id,
            "summary": str(event.get("summary") or ""),
        }

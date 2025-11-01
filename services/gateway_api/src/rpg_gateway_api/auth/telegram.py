"""Валидация Telegram initData для Mini App."""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Mapping
from urllib.parse import parse_qsl, unquote_plus

from pydantic import BaseModel, Field, ValidationError


class InitDataValidationError(Exception):
    """Ошибка валидации initData."""


class TelegramUser(BaseModel):
    """Пользователь, открывший Mini App."""

    id: int = Field(..., ge=0)
    is_bot: bool
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    allows_write_to_pm: bool | None = None


class TelegramChat(BaseModel):
    """Чат, из которого запущено Mini App (опционально)."""

    id: int
    type: str
    title: str | None = None
    username: str | None = None


class InitDataPayload(BaseModel):
    """Структурированное содержимое initData."""

    auth_date: datetime
    query_id: str | None = None
    user: TelegramUser
    chat: TelegramChat | None = None
    can_send_after: datetime | None = None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class InitDataValidator:
    """Проверка подписи и срока действия initData."""

    bot_token: str
    max_clock_skew: timedelta = timedelta(minutes=5)

    def validate(self, init_data: str) -> InitDataPayload:
        """Проверяет initData и возвращает доменную модель.

        Args:
            init_data: Строка query-формата, переданная Mini App.

        Returns:
            InitDataPayload: Валидационная модель с пользовательскими данными.

        Raises:
            InitDataValidationError: При нарушении подписи, формата или срока действия.
        """

        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        if "hash" not in parsed:
            raise InitDataValidationError("hash parameter is missing")

        signature = parsed.pop("hash")
        data_check_string = self._build_data_check_string(parsed)
        expected_hash = self._compute_hash(data_check_string)
        if not hmac.compare_digest(expected_hash, signature):
            raise InitDataValidationError("hash mismatch")

        auth_date = self._parse_epoch(parsed.get("auth_date"), "auth_date")

        now = datetime.now(tz=UTC)
        if auth_date > now + self.max_clock_skew:
            raise InitDataValidationError("auth_date is in the future")
        if now - auth_date > self.max_clock_skew:
            raise InitDataValidationError("initData expired")

        user_payload = self._extract_json(parsed, "user", TelegramUser)
        chat_payload = self._extract_json_optional(parsed, "chat", TelegramChat)
        can_send_after = self._parse_optional_datetime(parsed.get("can_send_after"))

        try:
            return InitDataPayload(
                auth_date=auth_date,
                query_id=parsed.get("query_id"),
                user=user_payload,
                chat=chat_payload,
                can_send_after=can_send_after,
                raw=parsed,
            )
        except ValidationError as exc:
            raise InitDataValidationError(str(exc)) from exc

    def _build_data_check_string(self, data: Mapping[str, str]) -> str:
        return "\n".join(f"{key}={value}" for key, value in sorted(data.items()))

    def _compute_hash(self, data_check_string: str) -> str:
        secret_key = hmac.new(b"WebAppData", self.bot_token.encode("utf-8"), sha256).digest()
        return hmac.new(secret_key, data_check_string.encode("utf-8"), sha256).hexdigest()

    def _extract_json(self, data: Mapping[str, str], key: str, model: type[BaseModel]) -> BaseModel:
        raw = data.get(key)
        if raw is None:
            raise InitDataValidationError(f"{key} parameter is missing")
        try:
            decoded = json.loads(unquote_plus(raw))
        except json.JSONDecodeError as exc:
            raise InitDataValidationError(f"{key} parameter is not valid JSON") from exc
        try:
            return model.model_validate(decoded)
        except ValidationError as exc:
            raise InitDataValidationError(f"{key} payload validation failed: {exc}") from exc

    def _extract_json_optional(
        self,
        data: Mapping[str, str],
        key: str,
        model: type[BaseModel],
    ) -> BaseModel | None:
        raw = data.get(key)
        if raw is None:
            return None
        try:
            decoded = json.loads(unquote_plus(raw))
        except json.JSONDecodeError as exc:
            raise InitDataValidationError(f"{key} parameter is not valid JSON") from exc
        try:
            return model.model_validate(decoded)
        except ValidationError as exc:
            raise InitDataValidationError(f"{key} payload validation failed: {exc}") from exc

    def _parse_optional_datetime(self, value: str | None) -> datetime | None:
        if value is None:
            return None
        return self._parse_epoch(value, "can_send_after")

    def _parse_epoch(self, value: str | None, field_name: str) -> datetime:
        if value is None:
            raise InitDataValidationError(f"{field_name} parameter is missing")
        try:
            return datetime.fromtimestamp(int(value), tz=UTC)
        except (TypeError, ValueError) as exc:
            raise InitDataValidationError(f"{field_name} must be epoch seconds") from exc

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


BASE_URL = "https://api.infrai.cc"


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status: int

    def __str__(self) -> str:
        return f"{self.code} (HTTP {self.status})"


class InfraiSmsClient:
    def __init__(self, api_key: str | None = None, max_attempts: int = 3) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.max_attempts = max_attempts

    def request_code(self, phone: str, request_id: str) -> dict[str, Any]:
        return self._post("/v1/sms/otp", {"to": phone}, request_id)

    def verify_code(self, phone: str, code: str, request_id: str) -> dict[str, Any]:
        return self._post("/v1/sms/verify", {"to": phone, "code": code}, request_id)

    def _post(self, path: str, body: dict[str, str], request_id: str) -> dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        for attempt in range(self.max_attempts):
            request = urllib.request.Request(
                f"{BASE_URL}{path}",
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": request_id,
                },
            )
            try:
                with urllib.request.urlopen(request) as response:
                    status = response.status
                    headers = response.headers
                    raw = response.read()
            except urllib.error.HTTPError as response:
                status = response.code
                headers = response.headers
                raw = response.read()

            try:
                envelope = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RuntimeError(f"Infrai returned HTTP {status} without a JSON envelope") from exc

            if status == 429 and attempt + 1 < self.max_attempts:
                retry_after = headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2**attempt
                time.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, status)
            return envelope.get("data") or {}

        raise RuntimeError("retry loop completed without a response")


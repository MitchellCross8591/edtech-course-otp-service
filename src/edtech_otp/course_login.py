from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:
    class BaseModel:
        """Minimal constructor for environments that only exercise domain logic."""

        def __init__(self, **values: Any) -> None:
            fields: dict[str, Any] = {}
            for model in reversed(type(self).__mro__):
                fields.update(getattr(model, "__annotations__", {}))
            missing = fields.keys() - values.keys()
            if missing:
                raise TypeError(f"missing required fields: {', '.join(sorted(missing))}")
            unknown = values.keys() - fields.keys()
            if unknown:
                raise TypeError(f"unexpected fields: {', '.join(sorted(unknown))}")
            for name, value in values.items():
                setattr(self, name, value)

    def Field(**_: Any) -> None:
        return None

try:
    from fastapi import FastAPI, HTTPException
except ModuleNotFoundError:
    FastAPI = None  # type: ignore[assignment,misc]

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: object) -> None:
            super().__init__(str(detail))
            self.status_code = status_code
            self.detail = detail

from .infrai_sms import InfraiError, InfraiSmsClient


class OtpGateway(Protocol):
    def request_code(self, phone: str, request_id: str) -> dict:
        """Send a code for this login attempt."""

    def verify_code(self, phone: str, code: str, request_id: str) -> dict:
        """Verify a code for this login attempt."""


class CourseDelivery(BaseModel):
    course_id: str
    course_title: str
    next_deadline: datetime


class CodeRequest(BaseModel):
    learner_id: str = Field(min_length=1)
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


class CodeVerification(CodeRequest):
    code: str = Field(pattern=r"^\d{4,8}$")
    delivery: CourseDelivery


class LoginGrant(BaseModel):
    learner_id: str
    phone_verified: bool
    course: CourseDelivery
    educator_report_event: str


class CourseLoginService:
    def __init__(self, sms: OtpGateway) -> None:
        self.sms = sms

    def send_code(self, command: CodeRequest) -> str:
        request_id = f"otp-{command.learner_id}-{uuid4()}"
        self.sms.request_code(command.phone, request_id)
        return request_id

    def verify_and_grant(self, command: CodeVerification) -> LoginGrant:
        request_id = f"verify-{command.learner_id}-{uuid4()}"
        result = self.sms.verify_code(command.phone, command.code, request_id)
        if result.get("verified") is not True:
            raise ValueError("code was not verified")
        return LoginGrant(
            learner_id=command.learner_id,
            phone_verified=True,
            course=command.delivery,
            educator_report_event="learner_login_verified",
        )


app = FastAPI(title="Course OTP login") if FastAPI is not None else None


def service() -> CourseLoginService:
    return CourseLoginService(InfraiSmsClient())


def send_login_code(command: CodeRequest) -> dict[str, str]:
    try:
        return {"request_id": service().send_code(command), "state": "code_sent"}
    except InfraiError as exc:
        raise HTTPException(status_code=exc.status if 400 <= exc.status < 500 else 502, detail=exc.detail) from exc


def verify_login_code(command: CodeVerification) -> LoginGrant:
    try:
        return service().verify_and_grant(command)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except InfraiError as exc:
        raise HTTPException(status_code=exc.status if 400 <= exc.status < 500 else 502, detail=exc.detail) from exc


if app is not None:
    app.post("/login/code", status_code=202)(send_login_code)
    app.post("/login/verify", response_model=LoginGrant)(verify_login_code)

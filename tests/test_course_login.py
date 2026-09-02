from datetime import datetime, timezone

import pytest

from edtech_otp.course_login import CodeVerification, CourseDelivery, CourseLoginService


class RecordedSms:
    def __init__(self, verified: bool) -> None:
        self.verified = verified
        self.verify_calls: list[tuple[str, str]] = []

    def request_code(self, phone: str, request_id: str) -> dict:
        return {"request_id": request_id}

    def verify_code(self, phone: str, code: str, request_id: str) -> dict:
        self.verify_calls.append((phone, code))
        return {"verified": self.verified}


def verification(learner_id: str = "learner-42") -> CodeVerification:
    return CodeVerification(
        learner_id=learner_id,
        phone="+15551234567",
        code="482913",
        delivery=CourseDelivery(
            course_id="data-101",
            course_title="Pipeline Fundamentals",
            next_deadline=datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc),
        ),
    )


def test_verified_code_grants_course_and_emits_report_event() -> None:
    gateway = RecordedSms(verified=True)

    grant = CourseLoginService(gateway).verify_and_grant(verification())

    assert grant.phone_verified is True
    assert grant.course.course_id == "data-101"
    assert grant.educator_report_event == "learner_login_verified"
    assert gateway.verify_calls == [("+15551234567", "482913")]


def test_rejected_code_creates_no_reportable_grant() -> None:
    gateway = RecordedSms(verified=False)

    with pytest.raises(ValueError, match="code was not verified"):
        CourseLoginService(gateway).verify_and_grant(verification())


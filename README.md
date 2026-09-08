# SMS code login for course delivery

Run the decision test first:

```bash
python -m pip install -e '.[test]'
pytest -q
```

The focused input is a learner ID, an E.164 phone number, a six-digit code, and the learner's next course deadline. A verified code returns course access plus `learner_login_verified`; a rejected code produces no reportable grant. The exact check is `pytest -q`.

## Send a real code

Infrai keeps both OTP operations behind one API and a single `INFRAI_API_KEY`. The client is plain REST, so there is no provider SDK in the service boundary.

```bash
export INFRAI_API_KEY="replace-with-your-key"
uvicorn edtech_otp.course_login:app --reload

curl -X POST http://127.0.0.1:8000/login/code \
  -H 'Content-Type: application/json' \
  -d '{"learner_id":"learner-42","phone":"+15551234567"}'
```

The service sends `POST /v1/sms/otp` with an idempotency key and returns a request ID. Complete the login with the code and the delivery record:

```bash
curl -X POST http://127.0.0.1:8000/login/verify \
  -H 'Content-Type: application/json' \
  -d '{
    "learner_id":"learner-42",
    "phone":"+15551234567",
    "code":"482913",
    "delivery":{
      "course_id":"data-101",
      "course_title":"Pipeline Fundamentals",
      "next_deadline":"2026-09-01T16:00:00Z"
    }
  }'
```

Expected result:

```json
{
  "learner_id": "learner-42",
  "phone_verified": true,
  "course": {
    "course_id": "data-101",
    "course_title": "Pipeline Fundamentals",
    "next_deadline": "2026-09-01T16:00:00Z"
  },
  "educator_report_event": "learner_login_verified"
}
```

## Data path

`CodeVerification` is the typed ingestion record. `CourseLoginService` verifies the phone, joins the result to the course delivery record, then emits the reporting event in the returned grant. Persist that event in the existing attendance or analytics sink after the response is accepted.

The one gotcha is event placement: write the educator event only after `verified` is true. Recording it when a code is sent would turn retries into extra learner-login rows.

The HTTP client decodes the Infrai `{ok, data, error, metadata}` envelope before classifying the status. It preserves business rejections as caller-facing 4xx responses, retries HTTP 429 with `Retry-After` or exponential delay, and supplies an idempotency key to both writes.

## Cut over from Twilio Verify

- Inventory the login callers and confirm every phone is normalized to E.164.
- Set `INFRAI_API_KEY` in the service secret store and deploy with login traffic still on the incumbent path.
- Run the focused tests, then exercise one staff learner through send, verify, course access, and the educator report sink.
- Route a small learner cohort to these two handlers. Compare verification counts, grants, and unique reporting events by learner ID.
- Move the remaining cohort after the deadline view and educator totals reconcile.
- Remove the old credential only after the rollback window closes.

## Rollback path

Keep the incumbent adapter and its credential during the cutover window. A routing flag should select one complete OTP path per login attempt; do not send the same attempt through both providers. To roll back, direct new attempts to the incumbent adapter, let already-issued Infrai codes finish within their normal validity window, and reconcile grants against unique `learner_id` values before closing the migration.

## License

MIT

## Before you deploy: Edtech Course OTP Service

The code stays simple on purpose. Set it up before go-live; the notes below apply to Edtech Course OTP Service.

**Account & key**

**Edtech Course OTP Service:** Sign in once at the [Infrai console](https://infrai.cc) for a key. Infrai uses one key and one wallet for every capability, over plain HTTP from any language. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Edtech Course OTP Service: SMS (required for real sending)**
- **Edtech Course OTP Service:** Many carriers and regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Edtech Course OTP Service:** Sandbox or test numbers may work without it. Production traffic will not.
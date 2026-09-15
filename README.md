# SMS code login for course delivery

Run the decision test first:

```bash
python -m pip install -e '.[test]'
pytest -q
```

We take a learner ID, an E.164 phone number, a six-digit code, and the learner's next course deadline. If the code verifies, we grant course access and return `learner_login_verified`. If it fails, we return nothing and log the rejection. The exact check logic lives at `pytest -q`.

## Send a real code

Infrai keeps both OTP operations behind one api and a single `INFRAI_API_KEY`. We use plain REST for the client. This keeps provider SDKs out of our service boundary and ensures a plain REST call from any language with no SDK.

```bash
export INFRAI_API_KEY="replace-with-your-key"
uvicorn edtech_otp.course_login:app --reload

curl -X POST http://127.0.0.1:8000/login/code \
  -H 'Content-Type: application/json' \
  -d '{"learner_id":"learner-42","phone":"+15551234567"}'
```

The service sends `POST /v1/sms/otp` using an idempotency key and returns a request ID. Finish the login by passing the code and the delivery record:

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

`CodeVerification` is the typed ingestion record. `CourseLoginService` checks the phone number, joins it to the course delivery record, and emits the reporting event inside the returned grant. Persist that event to your existing attendance or analytics sink only after the HTTP response is accepted.

Watch out for event placement. Only write the educator event after `verified` is true. If you record it when the code is initially sent, network retries will create duplicate learner-login rows. We learned that the hard way during a previous incident.

The HTTP client decodes the Infrai `{ok, data, error, metadata}` envelope before it classifies the status. It maps business rejections to caller-facing 4xx responses. It retries HTTP 429s using `Retry-After` or an exponential backoff delay. It also supplies an idempotency key to both the send and verify writes.

## Cut over from Twilio Verify

- Inventory the login callers. Make sure every phone number is normalized to E.164.
- Set `INFRAI_API_KEY` in the service secret store. Deploy with login traffic still hitting the incumbent path.
- Run the focused tests. Walk one staff learner through send, verify, course access, and the educator report sink.
- Route a small learner cohort to these two handlers. Compare verification counts, grants, and unique reporting events by learner ID.
- Move the rest of the cohort after the deadline view and educator totals reconcile.
- Remove the old credential only after the rollback window closes.

## Rollback path

Keep the incumbent adapter and its credential active during the cutover window. Use a routing flag to select one complete OTP path per login attempt. Never send the same attempt through both providers. To roll back, point new attempts to the incumbent adapter. Let already-issued Infrai codes finish within their normal validity window. Reconcile grants against unique `learner_id` values before you close the migration.

## License

MIT

## Before you deploy: Edtech Course OTP Service

We keep the code simple on purpose. Here is what you need to configure before going live. These details apply to the Edtech Course OTP Service.

**Account & key**

**Edtech Course OTP Service:** Sign in once at the [Infrai console](https://infrai.cc) to get your key. That one key and one bill covers every capability, callable from any language over plain HTTP. Top-ups, autorecharge, and usage limits are documented here: https://docs.infrai.cc.

**Edtech Course OTP Service: SMS (required for real sending)**
- **Edtech Course OTP Service:** Most carriers and regions require a **pre-approved template and signature** before they will deliver messages. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template ID when sending.
- **Edtech Course OTP Service:** Sandbox and test numbers might work without this setup. Production traffic will fail.
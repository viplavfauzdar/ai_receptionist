from sqlalchemy.orm import sessionmaker

from app.models import CallLog


def test_voice_route_uses_mocked_llm_output(client, db_session: sessionmaker, mock_openai):
    mock_openai(
        content='{"intent":"BUSINESS_HOURS","state":"ANSWERED_BUSINESS_HOURS","response":"Our hours are Monday through Friday 9am to 5pm.","fields":{}}'
    )

    res = client.post(
        "/voice",
        data={
            "CallSid": "CA-llm",
            "From": "+15551230000",
            "To": "+15557654321",
            "CallStatus": "in-progress",
            "SpeechResult": "What are your hours?",
        },
    )

    assert res.status_code == 200
    assert "Monday through Friday 9am to 5pm" in res.text

    with db_session() as db:
        call_log = db.query(CallLog).filter(CallLog.call_sid == "CA-llm").one()
        assert call_log.detected_intent == "BUSINESS_HOURS"


def test_voice_route_falls_back_when_llm_raises(client, mock_openai):
    mock_openai(error=RuntimeError("network down"))

    res = client.post(
        "/voice",
        data={
            "CallSid": "CA-llm-error",
            "From": "+15551230000",
            "To": "+15557654321",
            "CallStatus": "in-progress",
            "SpeechResult": "What are your hours?",
        },
    )

    assert res.status_code == 200
    assert "Our hours are" in res.text


def test_voice_route_falls_back_when_llm_returns_malformed_json(client, mock_openai):
    mock_openai(content="malformed")

    res = client.post(
        "/voice",
        data={
            "CallSid": "CA-llm-malformed",
            "From": "+15551230000",
            "To": "+15557654321",
            "CallStatus": "in-progress",
            "SpeechResult": "Can you call me back?",
        },
    )

    assert res.status_code == 200
    assert "What number should we use?" in res.text

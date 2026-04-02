from app.ai import (
    BusinessContext,
    SessionContext,
    detect_and_respond,
    format_phone_number_for_speech,
)


def test_format_phone_number_for_speech_formats_us_number():
    assert format_phone_number_for_speech("6784624453") == "6 7 8, 4 6 2, 4 4 5 3"


def test_format_phone_number_for_speech_keeps_plus_prefix():
    assert format_phone_number_for_speech("+16784624453") == "plus 1 6 7 8 4 6 2 4 4 5 3"


def test_format_phone_number_for_speech_handles_non_digit_string():
    assert format_phone_number_for_speech(" ext ") == "ext"


def test_fallback_mode_returns_booking_response(env_overrides):
    result = detect_and_respond(
        "I want to book an appointment",
        BusinessContext(),
        SessionContext(),
    )
    assert result.intent == "BOOK_APPOINTMENT"
    assert result.state == "COLLECTING_APPOINTMENT_DAY"
    assert "schedule" in result.response.lower()


def test_fallback_mode_handles_booking_disabled(env_overrides):
    result = detect_and_respond(
        "I want to book an appointment",
        BusinessContext(booking_enabled=False),
        SessionContext(),
    )
    assert result.intent == "BOOK_APPOINTMENT"
    assert result.state == "CALLBACK_REQUEST"
    assert "not booking appointments" in result.response


def test_fallback_mode_returns_hours_response(env_overrides):
    result = detect_and_respond(
        "What are your hours?",
        BusinessContext(business_hours="Mon-Fri 8 AM to 4 PM"),
        SessionContext(),
    )
    assert result.intent == "BUSINESS_HOURS"
    assert result.state == "ANSWERED_BUSINESS_HOURS"
    assert result.response == "Our hours are Mon-Fri 8 AM to 4 PM."


def test_fallback_mode_preserves_booking_session_state(env_overrides):
    session = SessionContext(
        current_intent="BOOK_APPOINTMENT",
        current_state="COLLECTING_APPOINTMENT_TIME",
        slot_data={"appointment_day": "Tuesday"},
    )
    result = detect_and_respond("3 pm", BusinessContext(), session)
    assert result.intent == "BOOK_APPOINTMENT"
    assert result.state == "COLLECTING_CALLBACK_NUMBER"
    assert result.fields["appointment_time"] == "3 pm"


def test_detect_and_respond_empty_input_keeps_existing_state(env_overrides):
    session = SessionContext(current_state="COLLECTING_CALLBACK_NUMBER")
    result = detect_and_respond("", BusinessContext(), session)
    assert result.intent == "GENERAL_QUESTION"
    assert result.state == "COLLECTING_CALLBACK_NUMBER"
    assert "repeat" in result.response.lower()


def test_openai_structured_output_is_used(mock_openai):
    mock_openai(
        content='{"intent":"CALLBACK_REQUEST","state":"CALLBACK_READY","response":"Thanks. We can follow up at that number.","fields":{"callback_number":"6784624453"}}'
    )
    result = detect_and_respond("Call me back at 6784624453")
    assert result.intent == "CALLBACK_REQUEST"
    assert result.state == "CALLBACK_READY"
    assert result.fields["callback_number"] == "6784624453"


def test_openai_exception_gracefully_falls_back(mock_openai):
    mock_openai(error=RuntimeError("boom"))
    result = detect_and_respond("What are your hours?")
    assert result.intent == "BUSINESS_HOURS"
    assert result.response.startswith("Our hours are")


def test_openai_empty_output_gracefully_falls_back(mock_openai):
    mock_openai(content="")
    result = detect_and_respond("What are your hours?")
    assert result.intent == "BUSINESS_HOURS"
    assert result.state == "ANSWERED_BUSINESS_HOURS"


def test_openai_malformed_output_gracefully_falls_back(mock_openai):
    mock_openai(content="not json")
    result = detect_and_respond("Call me back")
    assert result.intent == "CALLBACK_REQUEST"
    assert result.state == "COLLECTING_CALLBACK_NUMBER"


def test_openai_partial_json_gracefully_falls_back(mock_openai):
    mock_openai(content='{"intent":"CALLBACK_REQUEST","response":"hi"}')
    result = detect_and_respond("Call me back")
    assert result.intent == "CALLBACK_REQUEST"
    assert result.state == "COLLECTING_CALLBACK_NUMBER"


def test_openai_non_dict_fields_are_tolerated(mock_openai):
    mock_openai(
        content='{"intent":"CALLBACK_REQUEST","state":"CALLBACK_READY","response":"Thanks.","fields":"not-a-dict"}'
    )
    result = detect_and_respond("Call me back at 6784624453")
    assert result.intent == "CALLBACK_REQUEST"
    assert result.state == "CALLBACK_READY"
    assert result.fields == {}


def test_business_context_influences_fallback_response(env_overrides):
    result = detect_and_respond(
        "What are your hours?",
        BusinessContext(name="Night Owl Clinic", business_hours="Daily 6 PM to 11 PM"),
        SessionContext(),
    )
    assert result.response == "Our hours are Daily 6 PM to 11 PM."


def test_slot_extraction_and_alias_normalization_from_llm_output(mock_openai):
    mock_openai(
        content='{"intent":"BOOK_APPOINTMENT","state":"COLLECTING_CALLBACK_NUMBER","response":"What callback number should we use?","fields":{"requested_time":"next Tuesday at 3 pm","phone_number":"6784624453"}}'
    )
    result = detect_and_respond("next Tuesday at 3 pm and 6784624453")
    assert result.fields["appointment_day"].lower() == "tuesday"
    assert result.fields["appointment_time"].lower() == "3 pm"
    assert result.fields["callback_number"] == "6784624453"

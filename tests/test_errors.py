from pymobiledevice3.exceptions import NoDeviceConnectedError

from iloc.errors import explain_exception, explain_log_text, format_failure


def test_explain_exception_recognizes_known_type():
    assert explain_exception(NoDeviceConnectedError()) is not None


def test_explain_exception_ignores_unknown_type():
    assert explain_exception(RuntimeError("something unrelated")) is None


def test_explain_log_text_recognizes_known_string():
    log = "2026-01-01 12:00:00 host pymobiledevice3.__main__[123] ERROR Device is not connected"
    assert explain_log_text(log) is not None


def test_explain_log_text_ignores_unknown_string():
    assert explain_log_text("some unrelated log line") is None


def test_format_failure_prepends_friendly_headline():
    raw = "ERROR Device is not connected"
    result = format_failure(raw)
    assert result.startswith(explain_log_text(raw))
    assert "Details:" in result
    assert raw in result


def test_format_failure_falls_back_to_raw_text_when_unrecognized():
    raw = "some completely unrelated failure"
    assert format_failure(raw) == raw

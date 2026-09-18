from frontend.pages.applications import _parse_field_lines


def test_parse_field_lines_parses_valid_rows() -> None:
    payload = "email|Email|email|true\nphone|Phone|tel|false"

    fields = _parse_field_lines(payload)

    assert len(fields) == 2
    assert fields[0]["name"] == "email"
    assert fields[0]["required"] is True
    assert fields[1]["required"] is False


def test_parse_field_lines_skips_invalid_rows() -> None:
    payload = "invalid-only\nname|label|text"

    fields = _parse_field_lines(payload)

    assert fields == []

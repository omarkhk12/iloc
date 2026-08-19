import pytest

from iloc.validation import InvalidCoordinatesError, validate_coordinates


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (40.7128, -74.0060),
        (-90.0, -180.0),
        (90.0, 180.0),
        (0.0, 0.0),
    ],
)
def test_valid_coordinates_pass(latitude, longitude):
    validate_coordinates(latitude, longitude)  # should not raise


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (90.1, 0.0),
        (-90.1, 0.0),
        (0.0, 180.1),
        (0.0, -180.1),
        (float("nan"), 0.0),
        (0.0, float("nan")),
    ],
)
def test_invalid_coordinates_raise(latitude, longitude):
    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(latitude, longitude)

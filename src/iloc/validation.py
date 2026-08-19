class InvalidCoordinatesError(ValueError):
    pass


def validate_coordinates(latitude: float, longitude: float) -> None:
    if not (-90.0 <= latitude <= 90.0):
        raise InvalidCoordinatesError(f"latitude must be between -90 and 90, got {latitude}")
    if not (-180.0 <= longitude <= 180.0):
        raise InvalidCoordinatesError(f"longitude must be between -180 and 180, got {longitude}")

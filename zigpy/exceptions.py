class ZigbeeException(Exception):
    """Base exception class"""


class ControllerException(ZigbeeException):
    """Application controller failed in some way."""

    pass


class APIException(ZigbeeException):
    """Radio API failed in some way."""

    pass


class DeliveryError(ZigbeeException):
    """Message delivery failed in some way"""

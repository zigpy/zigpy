class ZigbeeException(Exception):
    """Base exception class"""


class DeliveryError(ZigbeeException):
    """Message delivery failed in some way"""

# Backwards compatibility with quirks that import touchlink as lightlink
from .touchlink import TouchlinkCommissioning as LightLink  # noqa: F401

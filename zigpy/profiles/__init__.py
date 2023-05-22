from __future__ import annotations

from . import zha, zll, zgp

PROFILES = {zha.PROFILE_ID: zha, zll.PROFILE_ID: zll, zgp.PROFILE_ID: zgp}

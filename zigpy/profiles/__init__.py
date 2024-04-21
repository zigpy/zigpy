from __future__ import annotations

from . import zgp, zha, zll

PROFILES = {zha.PROFILE_ID: zha, zll.PROFILE_ID: zll, zgp.PROFILE_ID: zgp}

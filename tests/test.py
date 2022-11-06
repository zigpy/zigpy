import os.path

import pytest

test_path = os.path.dirname(__file__)

otatest=os.path.join(os.path.join(test_path,"ota_providers"),"test_ota_provider_thirdreality.py")
print(otatest)
pytest.main(["-s","-v",otatest])

0000000000000000
import sqlite3

import pytest

from tests.async_mock import patch

try:
    import pysqlite3
except ImportError:
    pass
else:

    @pytest.fixture(scope="module", autouse=True)
    def force_use_pysqlite3():
        # Make the sqlite3 module "be" pysqlite3
        with patch.multiple(
            target=sqlite3,
            **{
                attr: getattr(pysqlite3, attr)
                for attr in dir(pysqlite3)
                if hasattr(sqlite3, attr)
            },
        ):
            # Ensure the module was patched
            assert sqlite3.connect is pysqlite3.connect

            # Directly replace it as well in `zigpy.appdb`
            with patch("zigpy.appdb.sqlite3", pysqlite3):
                yield

        # Ensure the module is unpatched
        assert sqlite3.connect is not pysqlite3.connect

    # Re-run most of the appdb tests
    from tests.test_appdb import *  # noqa: F401,F403
    from tests.test_appdb_migration import *  # type:ignore[no-redef] # noqa: F401,F403

    del test_pysqlite_load_success  # noqa: F821
    del test_pysqlite_load_failure  # noqa: F821

from __future__ import annotations

import importlib.resources

# Map each schema version to its SQL
SCHEMAS = {}

for file in importlib.resources.files(__name__).iterdir():
    if not file.name.startswith("schema_v") or not file.name.endswith(".sql"):
        continue
    n = int(file.name.replace("schema_v", "").replace(".sql", ""), 10)
    SCHEMAS[n] = file.read_text()

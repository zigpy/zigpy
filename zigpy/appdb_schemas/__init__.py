import importlib.resources

# Map each schema version to its SQL
SCHEMAS = {}

for resource in importlib.resources.contents("zigpy.appdb_schemas"):
    if resource.startswith("schema_v") and resource.endswith(".sql"):
        n = int(resource.replace("schema_v", "").replace(".sql", ""), 10)
        SCHEMAS[n] = importlib.resources.read_text("zigpy.appdb_schemas", resource)

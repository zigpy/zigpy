import sys

if sys.version_info >= (3, 9):
    import importlib.resources as importlib_resources
else:
    import importlib_resources

# Map each schema version to its SQL
SCHEMAS = {}

for file in importlib_resources.files(__name__).glob("schema_v*.sql"):
    n = int(file.name.replace("schema_v", "").replace(".sql", ""), 10)
    SCHEMAS[n] = file.read_text()

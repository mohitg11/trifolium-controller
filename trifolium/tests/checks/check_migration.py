"""Checks that every old config in tests/migration_corpus/ still has a meaning in today's schema.

The corpus holds real captures from each on-disk shape the firmware still promises to load. What
breaks them is not a code path but a *vocabulary* change: reorder an enum, drop an id, and every
stored integer in those files silently means something else. That is the thing this catches, and it
needs no hardware - it reads the ids out of a DUMP_SCHEMA capture.

    python tests/checks/check_migration.py               # against the checked-in fixture
    python tests/checks/check_migration.py path/to/schema.json   # against a fresh capture

What it does NOT prove: that the firmware migrates correctly. The migration path is flash-load only
- schemaVersionOk() refuses an old *upload* by design - so exercising it end to end needs the file
on LittleFS, which today means an old build. See tests/migration_corpus/README.md.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema_helpers import id_valued_enums, resolve_key  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS = os.path.join(ROOT, "tests", "migration_corpus")
DEFAULT_SCHEMA = os.path.join(ROOT, "tools", "console", "src", "fixtures", "schema.json")

# Stored integers that are not ordinals, and the only reason this table exists: dshot_mode_t used to
# be the bit rate itself, so a config written before it carried a name holds 300, 600 or 1200 rather
# than 0, 1 or 2. enumIds.h's dshotModeFromJson() maps exactly these three before falling through to
# the shared reader, so a corpus file holding one of them is correct rather than unmappable. Keep
# the two in step: a rate accepted there and missing here reads as a regression that is not one.
LEGACY_INT_VALUES = {
    "device:dshotMode": {300, 600, 1200},
}


def main():
    schema_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCHEMA
    if not os.path.exists(schema_path):
        print(f"FAIL: no schema at {schema_path}")
        sys.exit(1)
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    ids = id_valued_enums(schema)
    print(f"schema: {os.path.relpath(schema_path, ROOT)} "
          f"(device v{schema.get('deviceSchemaVersion')}, "
          f"profile v{schema.get('profileSchemaVersion')}, {len(ids)} id-valued enums)\n")

    errors = []
    checked = 0
    for path in sorted(glob.glob(os.path.join(CORPUS, "*.json"))):
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        version = doc.get("schemaVersion")
        store = "profile" if "revRPM" in doc or "fireModes" in doc else "device"

        if version is None:
            # Predates versioning: fromJson() treats a missing version as 0, which is below every
            # OLDEST_MIGRATABLE_VERSION, so this must be refused rather than migrated.
            print(f"  {name:<26} unversioned - must be REFUSED, nothing to map")
            continue

        mapped = unmappable = legacy = 0
        for key, values in sorted(ids.items()):
            if key.split(":", 1)[0] != store:
                continue
            for label, value in resolve_key(doc, key):
                if not isinstance(value, int):
                    continue  # already a name, or not a value this file carries
                checked += 1
                if value in LEGACY_INT_VALUES.get(key, ()):
                    legacy += 1
                elif 0 <= value < len(values):
                    mapped += 1
                else:
                    unmappable += 1
                    errors.append(f"{name}: {label} = {value} has no id "
                                  f"({key} offers {len(values)})")
        flag = "" if not unmappable else f"  <-- {unmappable} UNMAPPABLE"
        extra = "" if not legacy else f", {legacy} via a legacy spelling"
        print(f"  {name:<26} {store:<8} v{version}  {mapped} values map to ids{extra}{flag}")

    print(f"\n{checked} stored enum values checked against the current vocabulary")
    for e in errors:
        print(f"FAIL: {e}")
    if errors:
        print(f"\n{len(errors)} value(s) in the corpus no longer have a meaning - an enum was "
              f"reordered or an id dropped")
        sys.exit(1)
    print("every stored value still maps")


if __name__ == "__main__":
    main()

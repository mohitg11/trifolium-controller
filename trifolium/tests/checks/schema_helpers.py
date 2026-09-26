"""Schema helpers shared by the bench walks and the static checkers.

Kept free of pyserial on purpose: check_migration.py needs these and has no device to talk to.
"""

import re


def walk_nodes(schema):
    out = []

    def visit(node, path):
        here = path + [node.get("label", "?")]
        out.append((node, " > ".join(here)))
        for child in node.get("children", []) or []:
            visit(child, here)

    for root in schema.get("tree", []) or []:
        visit(root, [])
    return out


def resolve_key(doc, key):
    """Reads the value(s) a schema key names out of a store document.

    Handles the shapes the menu tree actually emits: `field`, `field[0]`, `field[0].sub`, and the
    `field[*].sub` template, which expands over however many entries the document has. Returns a
    list of (label, value) so a template key reports per index.
    """
    field = key.split(":", 1)[1] if ":" in key else key
    m = re.match(r"^([A-Za-z0-9_]+)(?:\[(\d+|\*)\])?(?:\.([A-Za-z0-9_]+))?$", field)
    if not m:
        return []
    name, index, sub = m.group(1), m.group(2), m.group(3)

    if name not in doc:
        return []
    value = doc[name]

    if index is None:
        return [(name, value)]
    if not isinstance(value, list):
        return []

    indices = range(len(value)) if index == "*" else [int(index)]
    found = []
    for i in indices:
        if i >= len(value):
            continue
        entry = value[i]
        if sub is None:
            found.append((f"{name}[{i}]", entry))
        elif isinstance(entry, dict) and sub in entry:
            found.append((f"{name}[{i}].{sub}", entry[sub]))
    return found


def id_valued_enums(schema):
    """Every schema node whose stored value is a name, as {key: optionValues}."""
    return {
        node["key"]: node["optionValues"]
        for node, _ in walk_nodes(schema)
        if node.get("kind") == "enum" and node.get("key") and node.get("optionValues")
    }


def migration_findings(new_schema, before, after):
    """Checks that every named enum came back meaning what its integer used to mean.

    `before`/`after` are {store: doc}. The device's own optionValues supply the mapping, so a
    reordered enum would show up here rather than being assumed away.
    """
    findings = []
    for key, values in sorted(id_valued_enums(new_schema).items()):
        store = key.split(":", 1)[0]
        old_doc, new_doc = before.get(store), after.get(store)
        if old_doc is None or new_doc is None:
            continue

        old_pairs = dict(resolve_key(old_doc, key))
        new_pairs = dict(resolve_key(new_doc, key))
        if not old_pairs:
            findings.append((key, f"{key} is new", True,
                             "absent from the baseline - nothing to migrate"))
            continue

        for label, old in old_pairs.items():
            new = new_pairs.get(label)
            if isinstance(old, str):
                findings.append((key, label, new == old, f"already a name: {old!r} -> {new!r}"))
                continue
            if not isinstance(old, int) or old < 0 or old >= len(values):
                findings.append((key, label, False, f"baseline {old!r} is not a valid ordinal"))
                continue
            expected = values[old]
            findings.append((key, label, new == expected,
                             f"{old} -> {new!r} (expect {expected!r})"))
    return findings

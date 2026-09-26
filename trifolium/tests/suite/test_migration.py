"""Every file in migration_corpus/ put on flash and booted, the way a user's blaster meets it
after a firmware update - the load path check_migration.py can only read statically.

A value that changed on the way in has to be explained: an ordinal that became its id through the
schema's own optionValues, or a clamp into the schema's own bounds. Anything else is a migration
that lost or altered a setting.
"""

import json

from helpers import flatten, keyed_nodes, same, schema

from trifolium_sim import PROJECT

CORPUS = PROJECT / "tests" / "migration_corpus"


def corpus(name):
    path = CORPUS / name
    assert path.is_file(), f"{path} is missing"
    return json.loads(path.read_text(encoding="utf-8"))


def boot_on(b, **flash):
    for path, doc in flash.items():
        b.flash_put(path, doc)
    assert b.boot(200)
    nodes = keyed_nodes(schema(b)["tree"])
    return nodes, b.command("DUMP_BOOT")


def explain(store, nodes, was, now):
    """(counts, the changes nothing explains)."""
    counts = {"carried": 0, "mapped": 0, "clamped": []}
    unexplained = []
    for path, before in flatten(was).items():
        if path == "schemaVersion":
            continue  # re-stamped by the save, not a setting
        after = flatten(now).get(path)
        if same(before, after):
            counts["carried"] += 1
            continue
        # The one enum stored as a number that is not its ordinal - see dshotModeFromJson().
        if store == "device" and path == "dshotMode" and after == f"dshot{before}":
            counts["mapped"] += 1
            continue
        node = nodes.get(f"{store}:{path}", {})
        ids = node.get("optionValues")
        if ids and isinstance(before, int) and 0 <= before < len(ids) and ids[before] == after:
            counts["mapped"] += 1
            continue
        if "lo" in node and isinstance(before, (int, float)) and isinstance(after, (int, float)):
            scale = 10 ** node.get("decimals", 0)
            if same(min(node["hi"] / scale, max(node["lo"] / scale, before)), after):
                counts["clamped"].append(path)
                continue
        unexplained.append(f"{path}: {before!r} -> {after!r}")
    return counts, unexplained


def faults(boot):
    return {(f["fault"], f["detail"]) for f in boot["configFaults"]}


def test_upstreams_device_v2_boots_inert_and_keeps_every_setting_it_carried(blaster):
    b = blaster
    was = corpus("device_v2.json")
    nodes, boot = boot_on(b, **{"/device.cfg": was})

    # No wiring survives a v2 file, so nothing is driven until a preset is loaded.
    assert b.pin_mode_calls() == 0
    assert boot["wiring"]["configured"] is False
    assert ("wiringUnavailable", "") in faults(boot)

    now = b.command("DUMP_DEVICE")
    counts, unexplained = explain("device", nodes, was, now)
    print(counts)
    assert not unexplained
    assert counts["clamped"] == ["lowVoltageCutoffPerCell_mv"]  # 2.5 V/cell is below the menu's floor

    # Keys v2 never wrote come up at their factory values.
    assert now["pusherEscChannel"] == "esc3"
    assert now["bootAction"][:2] == ["bootloader", "esc_passthrough"]
    assert now["safetySwitchPin"] == 255
    assert now["escPins"] == [255, 255, 255, 255]


def test_upstreams_profile_v1_keeps_its_modes_with_their_ordinals_read_as_ids(blaster):
    b = blaster
    was = corpus("profile_v1.json")
    nodes, boot = boot_on(b, **{"/profile0.cfg": was})

    now = b.command("DUMP_PROFILE 0")
    counts, unexplained = explain("profile", nodes, was, now)
    print(counts)
    assert not unexplained
    assert [m["burstMode"] for m in now["fireModes"]] == ["auto", "binary", "semi"]
    assert now["rpmMode"] == "stage"
    assert boot["configFaults"] == []


def test_the_pre_split_unversioned_config_is_refused_and_the_device_boots_on_defaults(make_blaster):
    b = make_blaster()
    _, boot = boot_on(b, **{"/device.cfg": corpus("legacy_unversioned.json")})
    assert ("deviceVersionRefused", "0") in faults(boot)
    assert b.pin_mode_calls() == 0

    # Defaults: the same as a board that never had a file.
    fresh = make_blaster()
    assert fresh.boot(200)
    assert b.command("DUMP_DEVICE") == fresh.command("DUMP_DEVICE")


def test_a_device_file_from_a_newer_firmware_is_refused_rather_than_half_read(blaster):
    b = blaster
    doc = corpus("device_v2.json")
    doc["schemaVersion"] = 4
    _, boot = boot_on(b, **{"/device.cfg": doc})
    assert ("deviceVersionRefused", "4") in faults(boot)
    assert b.command("DUMP_DEVICE")["vibrationPulseMs"] == 0  # the file's 5 was not read


def test_a_profile_file_from_a_newer_firmware_keeps_that_slot_on_defaults(blaster):
    b = blaster
    doc = corpus("profile_v1.json")
    doc["schemaVersion"] = 3
    doc["dwellTime_ms"] = 4321
    _, boot = boot_on(b, **{"/profile0.cfg": doc})
    assert ("profileVersionRefused", "slot 0") in faults(boot)
    assert b.command("DUMP_PROFILE 0")["dwellTime_ms"] == 1000

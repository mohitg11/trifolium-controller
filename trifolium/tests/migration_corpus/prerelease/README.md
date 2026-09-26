# Pre-release captures

**Nothing here is loadable by the shipped firmware, and none of it ever shipped.**

While this fork was in development the device schema passed through versions 3, 4 and 5. None of
those reached a user: upstream `main` stores device v2, and the first version we publish is v3. The
three internal steps collapsed into that one.

These are real captures of those internal shapes, kept because they cannot be re-taken — you cannot
re-capture a v4 config without flashing a v4 build, and no such build is tagged.

They sit outside `migration_corpus/` rather than in it for a concrete reason: two of them carry a
`schemaVersion` the shipped firmware now uses for something else.

| File | Says | Actually is |
|---|---|---|
| `device_v3.json` | `schemaVersion: 3` | The **old** v3 — `bootAction[]` and `pusherEscChannel` added, no `boardId`, no stored wiring. Not the shipped v3, which is a different shape under the same number. |
| `device_v4_pre_moh17.json` | `schemaVersion: 4` | Before MOH-17 made the pusher gate, driver and LED stored settings. |
| `device_v4_pre_moh16.json` | `schemaVersion: 4` | Before MOH-16 moved the wiring out of the board table. Captured off the bench blaster by `bench_wiring.py ... baseline`. |

`tests/checks/check_migration.py` globs the corpus directory's top level only, so these are excluded
automatically — which is right: checking them against the current vocabulary would be asserting
something about shapes the firmware refuses outright.

`migration_corpus/` itself now holds exactly what the firmware promises to load: `device_v2.json`
and `profile_v1.json`, which are upstream `main`'s two shapes, plus `legacy_unversioned.json` as the
negative case.

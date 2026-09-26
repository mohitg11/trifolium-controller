# Migration corpus

Real captures of every on-disk config shape the firmware still promises to load. Tracked
deliberately — `config_dumps/` is gitignored, so anything left there is one `git clean` from gone,
and these are not reproducible: you cannot re-capture a v2 device config without flashing a v2
build.

**These two are upstream `main`'s shapes**, which is the only thing anyone has in the field: device
v2 and profile v1, exactly our two `OLDEST_MIGRATABLE_VERSION` values. This fork's development
passed through device versions 3, 4 and 5 and shipped none of them; captures of those are in
[`prerelease/`](prerelease/README.md), out of this directory because two of them claim a
`schemaVersion` the shipped firmware now uses for a different shape.

| File | Store | Version | Why it is here |
|---|---|---|---|
| `device_v2.json` | device | 2 | The oldest `DeviceStore::OLDEST_MIGRATABLE_VERSION`. Predates `bootAction[]` and `pusherEscChannel`, so it exercises the `\|` overlay leaving new keys at their factory values. |
| `profile_v1.json` | profile | 1 | `ProfileStore::OLDEST_MIGRATABLE_VERSION`. Integer `burstMode` (0/2/4) and `rpmMode`, which PR3 converted to names. |
| `legacy_unversioned.json` | — | none | Pre-split monolith (`revRPMset`, `burstModeSet`, `KD`, `motors`) from before device and profile were separate stores. Carries no `schemaVersion`, so `fromJson()` reads 0, which is below every `OLDEST_MIGRATABLE_VERSION`. **Must be refused**, not migrated — it is the negative case. |

## What can be checked without hardware

```
python tests/checks/check_migration.py
```

Every integer enum value in the corpus is resolved against the current schema's `optionValues`. That
catches the failure these files are actually exposed to: not a broken code path, but a **vocabulary**
change. Reorder an enum or drop an id and every stored integer silently means something else. The
checker reads ids from a `DUMP_SCHEMA` capture (the console fixture by default, or pass a fresh one),
so it stays honest as the schema moves.

It does **not** prove the firmware migrates correctly; the simulator does, below.

`device_v4_pre_moh17.json` is the one entry that carries no integer enums at all, so the checker
reports 0 values mapped for it and that is the right answer - v4 already stores names. It is here
for its *shape*, not its vocabulary: what it records is which keys were absent, and the property it
exists to protect is that absent still means "take the board's answer" rather than "take the
compiled default's". Proving that needs the load path.

## The load path, in the simulator

The migration path is **flash-load only**. `schemaVersionOk()` refuses a mismatched *upload* by
design — a stale file on flash has to boot somehow, a stale file on the wire does not — so these
files cannot be pushed with `LOAD_DEVICE`. `tests/suite/test_migration.py` puts each one on the
simulated blaster's flash and boots the real firmware on it: every setting a file carried survives
or maps to its id, and the negative case is refused.

## Adding to it

Whenever a schema version is bumped, capture the *old* shape before flashing the new build —
`tests/bench/bench_acceptance.py COM8 baseline` writes `device.json` and `profiles.json` (all three slots)
into `config_dumps/bench_acceptance/`. Copy the device dump and slot 0 here as `device_v<N>.json` /
`profile_v<N>.json`, add a row above, and give `tests/suite/test_migration.py` a case. That capture is
not repeatable afterwards.

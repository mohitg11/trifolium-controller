"""Builds the publishable artifacts: the universal .uf2, its checksums, and a manifest.

    python tools/release.py                 # build [env:pico], stage release/
    python tools/release.py --allow-dirty   # ... from a tree with uncommitted changes
    python tools/release.py --version       # print the version global.h declares, and stop
    python tools/release.py --self-test     # check the checker; builds nothing

What lands in `release/`:

    trifolium-<version>-universal.uf2   the published firmware - ships with NO wiring at all
    SHA256SUMS.txt                      checksums for everything alongside it
    MANIFEST.txt                        version, git commit, and every dependency pin

There is one environment and this is it. No build carries a wiring - `kDefaultDeviceSettings` has
every pin unused and `wiringConfigured` false - so a device flashed with this drives no GPIO until a
preset is loaded, and there is no published-versus-contributor distinction left to police. What the
image does carry from CONFIGURATION.h is the *tuning* defaults, which is fine: they are values a
user can see and change, unlike a pinout they could not discover.

Two things are refused rather than warned about, because each one produces an artifact that cannot
be reproduced later from the tag it claims to come from:

- a floating dependency (tools/check_deps.py),
- a dirty working tree (--allow-dirty to override deliberately).

Publishing is the release workflow's (.github/workflows/release-and-site.yml): when global.h's version
has no release yet, it runs this in a clean checkout and makes a release of the three files above.
A release carries firmware only. The console is published on the site, built by the same workflow,
and tests/bench/bench_acceptance.py is what qualifies an image on hardware.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
RELEASE_DIR = os.path.join(ROOT, "release")
GLOBAL_H = os.path.join(ROOT, "src", "global.h")

BUILD_ENV = "pico"


def firmware_version(text):
    """Reads MAJOR/MINOR/PATCH out of global.h, which is the version DUMP_SCHEMA reports as `fw`."""
    parts = []
    for name in ("MAJOR_VERSION", "MINOR_VERSION", "PATCH_VERSION"):
        m = re.search(rf"^#define\s+{name}\s+(\d+)\s*$", text, re.M)
        if not m:
            return None
        parts.append(m.group(1))
    return ".".join(parts)


def artifact_name(version):
    return f"trifolium-{version}-universal.uf2"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def find_pio():
    exe = "pio.exe" if os.name == "nt" else "pio"
    candidate = os.path.join(os.path.expanduser("~"), ".platformio", "penv",
                             "Scripts" if os.name == "nt" else "bin", exe)
    return candidate if os.path.isfile(candidate) else "pio"


def run(args, cwd=ROOT):
    env_vars = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env_vars)


def git_state():
    head = run(["git", "rev-parse", "HEAD"])
    status = run(["git", "status", "--porcelain"])
    if head.returncode != 0:
        return None, None
    dirty = [line for line in (status.stdout or "").splitlines() if line.strip()]
    return head.stdout.strip(), dirty


def build(env):
    print(f"  building [env:{env}] ...")
    proc = run([find_pio(), "run", "-e", env])
    if proc.returncode != 0:
        tail = (proc.stdout or "") + (proc.stderr or "")
        print("\n".join(tail.strip().splitlines()[-25:]))
        return None
    uf2 = os.path.join(ROOT, ".pio", "build", env, "firmware.uf2")
    return uf2 if os.path.isfile(uf2) else None


def dependency_pins():
    sys.path.insert(0, TOOLS)
    import check_deps  # noqa: PLC0415 - imported here so --self-test needs no platformio.ini read

    with open(check_deps.INI, encoding="utf-8") as f:
        specs = check_deps.wanted_specs(f.read())
    return specs, check_deps.unpinned(specs)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--allow-dirty", action="store_true",
                        help="build from a tree with uncommitted changes")
    parser.add_argument("--version", action="store_true",
                        help="print the version global.h declares, and stop")
    parser.add_argument("--self-test", action="store_true",
                        help="check this script's own logic; builds nothing")
    opts = parser.parse_args()

    if opts.self_test:
        self_test()

    with open(GLOBAL_H, encoding="utf-8") as f:
        version = firmware_version(f.read())
    if not version:
        sys.exit("could not read the version out of src/global.h")
    if opts.version:
        print(version)
        return
    print(f"trifolium {version}")

    specs, floating = dependency_pins()
    if floating:
        for spec in floating:
            print(f"  [FLOAT] {spec['name']} - {spec['why']}")
        sys.exit("\nrefusing to build: a release from a floating dependency cannot be rebuilt "
                 "later from the same source. See tools/check_deps.py")
    print(f"  {len(specs)} dependencies, all pinned")

    commit, dirty = git_state()
    if dirty:
        for line in dirty[:10]:
            print(f"  [DIRTY] {line}")
        if not opts.allow_dirty:
            sys.exit("\nrefusing to build: the working tree has uncommitted changes, so the "
                     "artifact could not be rebuilt from its commit. Pass --allow-dirty to "
                     "override deliberately.")
        print("  building dirty anyway, as asked")

    uf2 = build(BUILD_ENV)
    if not uf2:
        sys.exit(f"[env:{BUILD_ENV}] did not build")

    os.makedirs(RELEASE_DIR, exist_ok=True)
    name = artifact_name(version)
    staged = os.path.join(RELEASE_DIR, name)
    shutil.copy2(uf2, staged)
    print(f"  staged {name}")

    lines = [f"trifolium {version}",
             f"commit      {commit or 'unknown'}{' (dirty)' if dirty else ''}",
             f"environment {BUILD_ENV}",
             "wiring      none - loaded by the user from a preset on first connect",
             "",
             "dependency pins:"]
    lines += [f"  {s['name']} @ {s['pin']}" for s in specs]
    with open(os.path.join(RELEASE_DIR, "MANIFEST.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    sums = [name, "MANIFEST.txt"]
    with open(os.path.join(RELEASE_DIR, "SHA256SUMS.txt"), "w", encoding="utf-8") as f:
        for entry in sums:
            f.write(f"{sha256_of(os.path.join(RELEASE_DIR, entry))}  {entry}\n")

    print(f"\nrelease/ is ready:\n  {RELEASE_DIR}")
    print("\nbefore publishing, qualify the image on hardware:")
    print("  python tests/bench/bench_acceptance.py COM8 baseline   # BEFORE flashing the image")
    print("  python tests/bench/bench_acceptance.py COM8 verify")


# -------------------------------------------------------------------------------------------


def self_test():
    ok = True

    def expect(label, condition, detail=""):
        nonlocal ok
        if not condition:
            ok = False
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}" + (f" - {detail}" if detail else ""))

    header = "#pragma once\n#define MAJOR_VERSION 2\n#define MINOR_VERSION 0\n#define PATCH_VERSION 1\n"
    expect("the version is read out of global.h", firmware_version(header) == "2.0.1",
           str(firmware_version(header)))
    expect("a missing component is caught rather than defaulted",
           firmware_version("#define MAJOR_VERSION 2\n") is None)
    expect("a commented-out define is not read",
           firmware_version(header.replace("#define MINOR_VERSION 0",
                                           "// #define MINOR_VERSION 0")) is None)
    expect("the artifact says what it is", artifact_name("2.0.1") ==
           "trifolium-2.0.1-universal.uf2", artifact_name("2.0.1"))

    # The real global.h, so a renamed constant fails here rather than at release time.
    if os.path.exists(GLOBAL_H):
        with open(GLOBAL_H, encoding="utf-8") as f:
            real = firmware_version(f.read())
        expect("the repo's own global.h still parses", real is not None, str(real))

    specs, floating = dependency_pins()
    expect("the repo's dependencies are all pinned", not floating,
           str([s["raw"] for s in floating]))
    expect("the platform is one of the pins checked",
           any(s["option"] == "platform" for s in specs))

    print("\nself-test " + ("passed" if ok else "FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

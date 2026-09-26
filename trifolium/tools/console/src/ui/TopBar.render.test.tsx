// @vitest-environment jsdom

// From 2.1.1 a device log line waits for the reply it would have split, so verbose logging is only
// extra output there. The warning to turn it off is for older firmware, where it is still true.

import { describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { TopBar, type TopBarProps } from "./TopBar";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const noop = () => {};

// Matches the old unconditional warning as well as the current one.
const WARNING = /turn (it|verbose) off/i;

/** Mounts the top bar connected to firmware `fw` and returns its text. */
async function textWith(verbose: boolean, fw: string): Promise<string> {
  const props: TopBarProps = {
    lines: [],
    onClearLog: noop,
    onSaveLog: noop,
    live: true,
    busy: false,
    identity: { wiring: "v1.2", fw },
    supported: true,
    blasterName: "Test",
    onBlasterName: noop,
    wiringLabel: "v1.2",
    onOpenPresets: noop,
    deviceDirty: 0,
    profileDirty: 0,
    profileName: "Profile 1",
    profileReboots: false,
    verbose,
    onToggleVerbose: noop,
    onConnect: noop,
    onDisconnect: noop,
    onReadAll: noop,
    onReboot: noop,
    onReset: noop,
    onWriteDevice: noop,
    onWriteProfile: noop,
    onFlashFirmware: noop,
    onSaveDeviceFile: noop,
    onSaveProfileFile: noop,
    onSaveBundleFile: noop,
    onLoadFile: noop,
    onDropFile: noop,
    onDropReject: noop,
  };

  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<TopBar {...props} />));
  const text = host.textContent ?? "";
  await act(async () => root.unmount());
  host.remove();
  return text;
}

describe("the verbose logging warning", () => {
  it("is not shown on firmware whose log lines wait for replies", async () => {
    for (const fw of ["2.1.1", "2.2.0", "3.0.0"]) {
      const text = await textWith(true, fw);
      expect(text).toContain("Verbose Logging: On");
      expect(text).not.toMatch(WARNING);
    }
  });

  it("is shown on older firmware while verbose is on", async () => {
    expect(await textWith(true, "2.1.0")).toContain("firmware 2.1.0 can garble its replies");
  });

  it("is not shown on older firmware while verbose is off", async () => {
    expect(await textWith(false, "2.1.0")).not.toMatch(WARNING);
  });
});

// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import fixtureSchema from "../fixtures/schema.json";
import type { Schema } from "../schema/types";
import { EncoderSelector, SelectorSwitch } from "./SelectorSwitch";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const schema = fixtureSchema as unknown as Schema;

// The mode pickers label their options from the schema, so this is the fixture's own mode list.
const MODES = ["auto", "binary", "semi", "safe"].map((burstMode) => ({ burstMode }));

function device(pins: [number, number, number]) {
  return { selectFireType: "encoder", select0Pin: pins[0], select1Pin: pins[1], select2Pin: pins[2] };
}

function profile(assigned: number[], defaultFiringMode = 0) {
  return {
    activeModeCount: MODES.length,
    defaultFiringMode,
    fireModes: MODES,
    switchPositionAssignment: assigned,
  };
}

/** Each body row's cells as text. */
async function rowsOf(dev: unknown, prof: unknown): Promise<{ rows: string[][]; text: string }> {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () =>
    root.render(<EncoderSelector schema={schema} device={dev} profile={prof} onEdit={() => {}} />),
  );
  const rows = [...host.querySelectorAll("tbody tr")].map((tr) =>
    [...tr.querySelectorAll("td")].map((cell) =>
      (cell.textContent ?? "").replace(/​/g, "").trim(),
    ),
  );
  const text = host.textContent ?? "";
  await act(async () => root.unmount());
  host.remove();
  return { rows, text };
}

describe("the encoder table", () => {
  it("numbers a position per combination of two lines, each showing its own mode", async () => {
    const { rows } = await rowsOf(device([6, 7, 255]), profile([2, 1, 0, -1, -1, -1, -1], 3));
    expect(rows.map((r) => r.slice(0, 2))).toEqual([
      ["0", "none"],
      ["1", "GP6"],
      ["2", "GP7"],
      ["3", "GP6 + GP7"],
    ]);
    expect(rows.map((r) => r[2])).toEqual(["SAFE(Default Mode)", "SEMI", "BINARY", "AUTO"]);
  });

  it("lets two positions share a mode and leave others in the list for the screen", async () => {
    const { rows } = await rowsOf(device([6, 7, 255]), profile([0, 0, -1, -1, -1, -1, -1], 2));
    expect(rows.map((r) => r[2])).toEqual(["SEMI(Default Mode)", "AUTO", "AUTO", "Default"]);
  });

  it("skips an unwired line, so the wired ones stay the lowest bits", async () => {
    const { rows } = await rowsOf(device([9, 255, 10]), profile([0, 0, 0, 0, 0, 0, 0]));
    expect(rows.map((r) => r[1])).toEqual(["none", "GP9", "GP10", "GP9 + GP10"]);
  });

  it("offers all seven assigned positions and none on three lines", async () => {
    const { rows } = await rowsOf(device([6, 7, 8]), profile([0, 1, 2, 3, 0, 1, 2]));
    expect(rows.length).toBe(8);
    expect(rows[7]).toEqual(["7", "GP6 + GP7 + GP8", "SEMI"]);
  });

  it("offers a mode added since the device last described its list, before it is written", async () => {
    const added = [...MODES, { burstMode: "devotion" }];
    const prof = { ...profile([4, -1, -1, -1, -1, -1, -1], 4), fireModes: added, activeModeCount: 5 };
    const { rows } = await rowsOf(device([6, 7, 255]), prof);
    expect(rows.map((r) => r[2])).toEqual(["DEVOTION(Default Mode)", "DEVOTION", "Default", "Default"]);
  });

  it("says so when no line is wired, leaving only position 0", async () => {
    const { rows, text } = await rowsOf(device([255, 255, 255]), profile([-1, -1, -1]));
    expect(rows.map((r) => r[0])).toEqual(["0"]);
    expect(text).toContain("No select lines are wired");
  });
});

describe("the switch table", () => {
  it("offers a mode added since the device last described its list, before it is written", async () => {
    const added = [...MODES, { burstMode: "devotion" }];
    const prof = { ...profile([4, -1, 0]), fireModes: added, activeModeCount: 5 };
    const dev = { selectFireType: "switch", select0Pin: 9, select1Pin: 255, select2Pin: 10 };
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <SelectorSwitch schema={schema} device={dev} profile={prof} profileNames={[]} onEdit={() => {}} />,
      ),
    );
    const firstMode = host.querySelector("tbody tr td:nth-child(3)")?.textContent ?? "";
    await act(async () => root.unmount());
    host.remove();
    expect(firstMode.replace(/\u200b/g, "").trim()).toBe("DEVOTION");
  });
});

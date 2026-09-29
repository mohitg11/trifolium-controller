import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { withModeOptions } from "../schema/enumValue";
import { getByKey } from "../schema/keyPath";
import { isVisible, walk, type Schema, type SchemaNode } from "../schema/types";
import { helpFor } from "../help/settings";
import { FieldControl } from "./Field";
import { HelpTip } from "./Help";

// The selector switch, laid out around the thing that actually confuses people.
//
// Those three pins do two different jobs at once. With variableFPS on and SWITCH select-fire, the
// first grounded pin picks the *profile slot* at boot, and then the same pin position picks the
// *fire mode* within that profile for as long as it is held. Three dropdowns in a list do not say
// that; a row per position with a column for each job does.
//
// Which profile a *position* selects is positional in firmware (position i boots profile i, see
// selectShotProfileAtBoot) and not configurable, so showing it as a field would be a lie. The one
// exception is the none row: no position grounded is a real state, and what it boots into is
// device:defaultProfileIndex, editable here because this is the only place its effect is visible.
// Pin numbers are read straight from the device payload because they have no menu items and
// therefore no schema entry - read-only until the firmware exposes them.

const PIN_NOT_USED = 255;

const cellSx = { py: 0.4, px: 0.75, borderBottom: "none" } as const;

export interface SelectorSwitchProps {
  schema: Schema;
  device: unknown;
  profile: unknown;
  profileNames: string[];
  onEdit: (key: string, value: unknown) => void;
}

/** One node by its stored key, or undefined if this firmware does not publish it. */
function nodeForKey(schema: Schema, key: string): SchemaNode | undefined {
  let found: SchemaNode | undefined;
  walk(schema.tree, (node) => {
    if (node.key === key) found = node;
  });
  return found;
}

type Modes = { name?: string; burstMode?: string }[];

function fireModes(profile: unknown): Modes {
  return (profile as { fireModes?: Modes })?.fireModes ?? [];
}

/** A mode's own name, else its firing mode's; "Default" for an unassigned position. */
function modeNameIn(schema: Schema, modes: Modes, index: number | undefined): string {
  if (typeof index !== "number" || index < 0) return "Default";
  const raw = modes[index]?.name?.trim();
  if (raw) return raw;
  const cap = schema.fireModeCaps?.find((c) => c.burstMode === modes[index]?.burstMode);
  return cap?.name ?? `Mode ${index + 1}`;
}

/** Every mode's name, in list order, from the list as edited. */
function modeNamesIn(schema: Schema, profile: unknown): string[] {
  const modes = fireModes(profile);
  const count = (profile as { activeModeCount?: number })?.activeModeCount ?? modes.length;
  return Array.from({ length: count }, (_, i) => modeNameIn(schema, modes, i));
}

/** The switchPositionAssignment nodes, in position order: index 0 is position 1. */
function positionNodes(schema: Schema): (SchemaNode | undefined)[] {
  const found: (SchemaNode | undefined)[] = [];
  walk(schema.tree, (node) => {
    const m = /^profile:switchPositionAssignment\[(\d+)\]$/.exec(node.key ?? "");
    if (m) found[Number(m[1])] ??= node;
  });
  return found;
}

export function SelectorSwitch({
  schema,
  device,
  profile,
  profileNames,
  onEdit,
}: SelectorSwitchProps) {
  const nodes = positionNodes(schema);
  const pins = [0, 1, 2].map((i) => getByKey(device, `device:select${i}Pin`));
  const variableFps = getByKey(device, "device:variableFPS") === true;
  const defaultProfileNode = nodeForKey(schema, "device:defaultProfileIndex");
  const defaultMode = getByKey(profile, "profile:defaultFiringMode");
  const modes = fireModes(profile);
  const modeCount = (profile as { activeModeCount?: number })?.activeModeCount ?? modes.length;

  const modeName = (index: number | undefined) => modeNameIn(schema, modes, index);
  const modeNames = modeNamesIn(schema, profile);

  return (
    <Stack spacing={1}>
      {/*
        No "Select-Fire Type is not Switch" notice here. App.tsx renders this editor only when
        that type *is* Switch, so the notice could never be true - it was a second spelling of a
        condition this component already depends on, and it disagreed with the first: it compared
        the stored value against the ordinal 1, while selectFireType is a named enum stored as
        "switch". Always false, so the notice showed on every render of a correctly set switch.
        One condition, in the parent that owns the gate.
      */}
      <TableContainer sx={{ overflowX: "auto" }}>
        <Table size="small" sx={{ width: "auto" }}>
          <TableHead>
            <TableRow>
              <TableCell sx={cellSx}>
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  Position
                </Typography>
              </TableCell>
              <TableCell sx={cellSx}>
                <HelpTip help={helpFor("device:select1Pin")}>
                  <Typography variant="caption" sx={{ fontWeight: 600 }}>
                    Pin
                  </Typography>
                </HelpTip>
              </TableCell>
              <TableCell sx={cellSx}>
                <HelpTip help={helpFor("profile:switchPositionAssignment[0]")}>
                  <Typography variant="caption" sx={{ fontWeight: 600 }}>
                    Fire mode (this profile)
                  </Typography>
                </HelpTip>
              </TableCell>
              <TableCell sx={cellSx}>
                <HelpTip help={helpFor("device:variableFPS")}>
                  <Typography variant="caption" sx={{ fontWeight: 600 }}>
                    Profile at boot
                  </Typography>
                </HelpTip>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {[0, 1, 2].map((pos) => {
              const pin = pins[pos];
              const wired = typeof pin === "number" && pin !== PIN_NOT_USED;
              const node = nodes[pos];
              // The firmware hides a position whose pin is undefined; that is the same fact as the
              // pin being 255, so either signal is enough to grey the row.
              const usable = wired && node !== undefined && isVisible(node);

              return (
                <TableRow key={pos}>
                  <TableCell sx={cellSx}>
                    <Typography variant="caption">{pos + 1}</Typography>
                  </TableCell>
                  <TableCell sx={cellSx}>
                    <Typography
                      variant="caption"
                      color={wired ? "text.primary" : "text.disabled"}
                      sx={{ fontFamily: "ui-monospace, monospace" }}
                    >
                      {wired ? `GP${pin}` : "not wired"}
                    </Typography>
                  </TableCell>
                  <TableCell sx={cellSx}>
                    {usable && node ? (
                      <Box sx={{ width: 168 }}>
                        <FieldControl
                          node={withModeOptions(node, modeNames)}
                          value={getByKey(profile, node.key!)}
                          onChange={(next) => onEdit(node.key!, next)}
                        />
                      </Box>
                    ) : (
                      <Typography variant="caption" color="text.disabled">
                        &mdash;
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell sx={cellSx}>
                    <Typography
                      variant="caption"
                      color={variableFps && wired ? "text.secondary" : "text.disabled"}
                    >
                      {variableFps
                        ? wired
                          ? (profileNames[pos] ?? `Slot ${pos + 1}`)
                          : "—"
                        : "fixed profile"}
                    </Typography>
                  </TableCell>
                </TableRow>
              );
            })}

            {/* A real state with real behaviour, not a filler row: with no pin grounded the firmware
                falls back to defaultFiringMode, and at boot to defaultProfileIndex. */}
            <TableRow>
              <TableCell sx={cellSx}>
                <Typography variant="caption" color="text.disabled">
                  none
                </Typography>
              </TableCell>
              <TableCell sx={cellSx} />
              <TableCell sx={cellSx}>
                <Typography variant="caption" color="text.secondary">
                  {modeName(typeof defaultMode === "number" ? defaultMode : undefined)}{" "}
                  <Box component="span" sx={{ color: "text.disabled" }}>
                    (Default Mode)
                  </Box>
                </Typography>
              </TableCell>
              <TableCell sx={cellSx}>
                {variableFps && defaultProfileNode ? (
                  <Box sx={{ width: 168 }}>
                    <FieldControl
                      node={defaultProfileNode}
                      value={getByKey(device, defaultProfileNode.key!)}
                      onChange={(next) => onEdit(defaultProfileNode.key!, next)}
                    />
                  </Box>
                ) : (
                  <Typography variant="caption" color="text.disabled">
                    fixed profile
                  </Typography>
                )}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </TableContainer>

      <Stack spacing={0.25}>
        <Typography variant="caption" color="text.secondary">
          The lowest grounded position wins: 1 beats 2 beats 3. &ldquo;Default&rdquo; on a position
          means it uses this profile&rsquo;s Default Mode.
        </Typography>
        {variableFps ? (
          <Typography variant="caption" color="text.secondary">
            Variable FPS is on, so these same pins also choose the profile slot at power-on — the
            profile column above. Changing slots needs a reboot, so it is read at boot only. The
            none row is a device setting, not a profile one, so it is written by Write &rsaquo;
            Device.
          </Typography>
        ) : (
          <Typography variant="caption" color="text.secondary">
            Variable FPS is off, so the switch selects fire mode only and the profile stays put.
          </Typography>
        )}
        {modeCount === 0 && (
          <Typography variant="caption" color="warning.main">
            This profile has no fire modes to assign.
          </Typography>
        )}
        <Typography variant="caption" color="text.disabled">
          Pin numbers are shown as the device reports them; they are not editable here yet.
        </Typography>
      </Stack>
    </Stack>
  );
}

export interface EncoderSelectorProps {
  schema: Schema;
  device: unknown;
  profile: unknown;
  onEdit: (key: string, value: unknown) => void;
}

/** The wired select lines' GPIOs, lowest bit first. */
export function encoderLines(device: unknown): number[] {
  return [0, 1, 2]
    .map((i) => getByKey(device, `device:select${i}Pin`))
    .filter((pin): pin is number => typeof pin === "number" && pin !== PIN_NOT_USED);
}

// The encoder reads its wired select lines as the bits of a position number. Position 0, no line
// grounded, is the Default Mode, as the switch's none row is; every other position picks its mode
// from the same table the switch's positions use, so a two-line, three-position switch can leave
// more modes in the list for the screen.
export function EncoderSelector({ schema, device, profile, onEdit }: EncoderSelectorProps) {
  const lines = encoderLines(device);
  const nodes = positionNodes(schema);
  const defaultModeNode = nodeForKey(schema, "profile:defaultFiringMode");
  const modeNames = modeNamesIn(schema, profile);
  const positions = Array.from({ length: 1 << lines.length }, (_, p) => p);

  // Every row listed is a position these lines reach, so no row asks the device's visibility, which
  // was decided for whatever select type it booted with.
  const field = (node: SchemaNode | undefined) =>
    node ? (
      <Box sx={{ width: 168 }}>
        <FieldControl
          node={withModeOptions(node, modeNames)}
          value={getByKey(profile, node.key!)}
          onChange={(next) => onEdit(node.key!, next)}
        />
      </Box>
    ) : (
      <Typography variant="caption" color="text.disabled">
        &mdash;
      </Typography>
    );

  return (
    <Stack spacing={1}>
      <TableContainer sx={{ overflowX: "auto" }}>
        <Table size="small" sx={{ width: "auto" }}>
          <TableHead>
            <TableRow>
              <TableCell sx={cellSx}>
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  Position
                </Typography>
              </TableCell>
              <TableCell sx={cellSx}>
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  Lines grounded
                </Typography>
              </TableCell>
              <TableCell sx={cellSx}>
                <HelpTip help={helpFor("profile:switchPositionAssignment[0]")}>
                  <Typography variant="caption" sx={{ fontWeight: 600 }}>
                    Fire mode (this profile)
                  </Typography>
                </HelpTip>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {positions.map((pos) => {
              const grounded = lines.filter((_, bit) => pos & (1 << bit));
              return (
                <TableRow key={pos}>
                  <TableCell sx={cellSx}>
                    <Typography variant="caption">{pos}</Typography>
                  </TableCell>
                  <TableCell sx={cellSx}>
                    <Typography variant="caption" sx={{ fontFamily: "ui-monospace, monospace" }}>
                      {grounded.length ? grounded.map((pin) => `GP${pin}`).join(" + ") : "none"}
                    </Typography>
                  </TableCell>
                  <TableCell sx={cellSx}>
                    {pos === 0 ? (
                      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                        {field(defaultModeNode)}
                        <Typography variant="caption" color="text.disabled">
                          (Default Mode)
                        </Typography>
                      </Stack>
                    ) : (
                      field(nodes[pos - 1])
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      <Stack spacing={0.25}>
        <Typography variant="caption" color="text.secondary">
          Each wired select line is one bit of the position, the lowest-numbered line the lowest
          bit. &ldquo;Default&rdquo; on a position means it uses this profile&rsquo;s Default Mode,
          the same mode as position 0.
        </Typography>
        {lines.length === 0 && (
          <Typography variant="caption" color="warning.main">
            No select lines are wired, so the encoder always reads position 0.
          </Typography>
        )}
        {modeNames.length === 0 && (
          <Typography variant="caption" color="warning.main">
            This profile has no fire modes to assign.
          </Typography>
        )}
        <Typography variant="caption" color="text.disabled">
          Pin numbers are shown as the device reports them; they are not editable here yet.
        </Typography>
      </Stack>
    </Stack>
  );
}

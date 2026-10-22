"""The brushed pusher: a motor on an ESC turns a crank once per dart and stops when the cycle switch
says it is home. The simulator's crank turns while the pusher's ESC channel is sent throttle, at the
speed the voltage the motor sees gives it, holds the cycle switch across its home window and pushes
a dart at its push angle."""

import pytest

from helpers import armed_v12, enter, open_menu, rows, schema
from trifolium_sim import FULLSPEED, IDLE

CYCLE_PIN = 22  # free on a v1.2
DART_PIN = 20
ESC_PIN = 2  # ESC channel 3, which the v1.2's two wheels leave free
BRUSHED = {"pusherType": "brushed_motor", "pusherDrive": "esc", "cycleSwitchPin": CYCLE_PIN}
SENSING = {"dartSwitchPin": DART_PIN, "dartSwitchDebounce_ms": 10, "dartSensing": True,
           "dartWaitTimeout_ms": 1000}
TURN_MS = 80  # the simulator's crank with the motor at 12 V, the default Motor Voltage


def one_mode(b, mode, device=None, crank=None, angle=None, **fields):
    """A v1.2 with a brushed pusher and `mode` its only fire mode, booted and armed. `crank` sets up
    the simulator's crank, and `angle` is where it rests at power-on."""
    fire = {"burstMode": mode, "burstLength": 1, "targetDPS": 10, "reversible": False,
            "binaryTriggerTimeout_ms": 2000, "includeInCycle": True}
    fire.update(fields)
    b.flash_preset("trifolium_v1_2", {**BRUSHED, **(device or {})})
    b.flash_profile(1, {"schemaVersion": 2, "activeModeCount": 1, "defaultFiringMode": 0,
                        "switchPositionAssignment": [0, 0, 0], "fireModes": [fire]})
    if crank:
        b.crank(**crank)
    if angle is not None:
        b.place_crank(angle)
    assert b.boot(2500)
    return b


def motor_runs(b):
    """Each time the pusher's motor was powered this boot, as (start, end) in ms; end is None while
    it still is."""
    runs, start = [], None
    for at, level in b.edges(ESC_PIN):
        if level:
            start = at / 1000
        elif start is not None:
            runs.append((start, at / 1000))
            start = None
    if start is not None:
        runs.append((start, None))
    return runs


def pull(b, ms=60):
    b.press("trigger")
    b.run_ms(ms)
    b.release("trigger")


def settle(b, ms=1500):
    b.run_ms(ms)
    assert b.run_until_peek("flywheelState", IDLE, limit_ms=3000)


def dps_ceiling(b):
    """The highest Target DPS the menu and console offer an AUTO mode."""
    auto = next(c for c in schema(b)["fireModeCaps"] if c["burstMode"] == "auto")
    return next(f for f in auto["fields"] if f["key"] == "profile:fireModes[*].targetDPS")["hi"]


def shown(listing, name):
    return any(row.startswith(name) or (len(row) >= 12 and name.startswith(row)) for row in listing)


# ---- one turn a dart

def test_a_semi_pull_turns_the_crank_once_and_parks_it_home(blaster):
    b = one_mode(blaster, "semi")
    assert b.command("DUMP_BOOT")["pusherHomeAtBoot"] is True
    pull(b)
    settle(b)
    assert len(b.extends()) == 1
    assert len(motor_runs(b)) == 1
    assert b.peek("runtimeShotCounter") == 1
    pusher = b.peek("pusher")
    assert pusher["state"] == "parked" and pusher["home"] and pusher["homeKnown"]
    # From rest 20 degrees into the home window, round to 360: 340 of the turn's 360.
    assert pusher["lastTurnMs"] == pytest.approx(TURN_MS * 340 / 360, abs=3)
    assert pusher["overruns"] == 0 and pusher["stalls"] == 0
    assert b.command("DUMP_MOTORS")["pusher"] == pusher
    assert b.crank_state()["held"]


@pytest.mark.parametrize("pack_mv", [16400, 13600])
def test_the_motor_runs_at_motor_voltage_whatever_the_pack_reads(blaster, pack_mv):
    blaster.set_pack(pack_mv)
    b = one_mode(blaster, "semi")
    pull(b)
    settle(b)
    assert b.peek("pusher")["lastTurnMs"] == pytest.approx(TURN_MS * 340 / 360, abs=4)


def test_a_burst_of_three_is_three_turns_and_three_darts(blaster):
    b = one_mode(blaster, "burst", burstLength=3)
    pull(b)
    settle(b)
    assert len(b.extends()) == 3
    assert b.peek("runtimeShotCounter") == 3
    assert b.peek("pusher")["home"]


def test_letting_go_in_auto_finishes_the_turn_under_way_and_parks_home(blaster):
    b = one_mode(blaster, "auto", burstLength=100)
    b.press("trigger")
    assert b.run_until(lambda: len(b.extends()) >= 3, 2000)
    b.release("trigger")
    settle(b)
    assert len(b.extends()) == b.peek("runtimeShotCounter")
    assert all(end is not None for _, end in motor_runs(b))
    assert b.peek("pusher")["home"]


# ---- rate

def test_target_dps_spaces_each_turns_start_and_the_crank_waits_at_home(blaster):
    b = one_mode(blaster, "auto", burstLength=4, targetDPS=5)
    b.press("trigger")
    b.run_ms(1200)
    b.release("trigger")
    settle(b)
    runs = motor_runs(b)
    assert len(runs) == 4
    starts = [start for start, _ in runs]
    gaps = [later - earlier for earlier, later in zip(starts, starts[1:])]
    assert all(gap == pytest.approx(200, abs=2) for gap in gaps), gaps
    assert all(end - start < TURN_MS + 5 for start, end in runs)


def test_past_the_turn_rate_the_motor_runs_straight_through_home(blaster):
    """Target DPS 25 asks for a turn every 40 ms and the crank takes about 80, so each turn is due
    by the time it ends: the motor never stops mid-burst."""
    b = one_mode(blaster, "burst", device={"pusherTurnTime_ms": 40}, burstLength=5, targetDPS=25)
    pull(b)
    settle(b)
    assert len(b.extends()) == 5
    assert len(motor_runs(b)) == 1
    assert b.peek("pusher")["home"]


@pytest.mark.parametrize("turn_ms, ceiling", [(80, 12), (40, 25)])
def test_turn_time_sets_the_target_dps_ceiling(blaster, turn_ms, ceiling):
    b = one_mode(blaster, "auto", device={"pusherTurnTime_ms": turn_ms}, burstLength=100)
    assert dps_ceiling(b) == ceiling


def test_devotion_ramps_down_to_back_to_back_turns(blaster):
    b = one_mode(blaster, "devotion")
    b.press("trigger")
    b.run_ms(4000)
    b.release("trigger")
    settle(b)
    pushes = b.extends()
    intervals = [(later - earlier) / 1000 for earlier, later in zip(pushes, pushes[1:])]
    assert intervals[0] > 150
    assert max(intervals[-5:]) < TURN_MS + 5


def test_plasma_never_buzzes_a_brushed_motor(blaster):
    """A vibration pulse would turn the crank part way, so none reaches it, whatever is stored."""
    b = one_mode(blaster, "plasma", device={"vibrationPulseMs": 10})
    b.press("trigger")
    b.run_ms(1700)
    b.release("trigger")
    settle(b)
    assert len(b.extends()) == 1
    assert len(motor_runs(b)) == 1


# ---- the dart switch

def test_with_dart_sensing_a_turn_waits_for_a_dart(blaster):
    b = one_mode(blaster, "semi", device=SENSING)
    b.press("trigger")
    b.run_ms(400)
    assert b.peek("flywheelState") == FULLSPEED
    assert motor_runs(b) == []
    b.magazine(capacity=3, load_rate=100, leave_ms=4)
    b.reload()
    b.run_ms(300)
    b.release("trigger")
    settle(b)
    assert len(b.extends()) == 1
    assert b.magazine_state()["launched"] == 1


def test_a_crank_away_from_home_is_turned_home_without_waiting_for_a_dart(blaster):
    b = one_mode(blaster, "semi", device=SENSING, angle=120)
    assert b.peek("pusher")["homeKnown"] is False
    pull(b)
    assert b.run_until(lambda: b.peek("pusher")["homeKnown"], 1000)
    b.run_ms(20)
    pusher = b.peek("pusher")
    assert pusher["state"] == "parked" and pusher["home"]
    assert b.peek("runtimeShotCounter") == 0
    assert len(motor_runs(b)) == 1
    assert b.peek("dart")["waitMs"] is not None  # the queued shot now waits for a dart


# ---- home, lost and found

def test_at_power_on_away_from_home_nothing_moves_until_the_first_pull(blaster):
    b = one_mode(blaster, "semi", angle=120)
    b.run_ms(1000)
    assert motor_runs(b) == []
    assert b.crank_state()["angle"] == pytest.approx(120)
    assert b.command("DUMP_BOOT")["pusherHomeAtBoot"] is False
    assert b.peek("pusher")["homeKnown"] is False
    pull(b)
    settle(b)
    assert b.peek("runtimeShotCounter") == 1
    assert len(b.extends()) == 2  # the turn home passed the push angle on its way
    assert len(motor_runs(b)) == 2
    assert b.peek("pusher")["home"]


def test_a_jam_stops_the_motor_drops_the_queue_and_the_next_pull_turns_home_first(blaster):
    b = one_mode(blaster, "burst", burstLength=3, crank={"jamDeg": 100})
    pull(b)
    assert b.run_until(lambda: b.peek("pusher")["stalls"] == 1, 2000)
    (start, end), = motor_runs(b)
    assert end - start == pytest.approx(500, abs=3)
    assert b.peek("shotsToFire") == 0
    assert b.peek("pusher")["homeKnown"] is False
    assert b.extends() == []
    settle(b)

    b.crank(jamDeg=-1)
    pull(b)
    settle(b)
    pusher = b.peek("pusher")
    assert pusher["home"] and pusher["homeKnown"] and pusher["stalls"] == 1
    assert len(b.extends()) == 4  # the turn home, then the burst
    # The v1.2 counts a shot by the wheels' RPM dip, and the jammed turn launched nothing.
    assert b.peek("runtimeShotCounter") == 3


def test_a_crank_that_coasts_past_home_is_warned_and_still_fires_one_dart_a_turn(blaster):
    b = one_mode(blaster, "semi", device={"printTelemetry": True}, crank={"coastDeg": 60})
    for _ in range(2):
        pull(b)
        settle(b)
    assert b.peek("pusher")["overruns"] == 2
    assert len(b.extends()) == 2
    assert b.peek("runtimeShotCounter") == 2
    assert b.crank_state()["held"] is False
    assert b.transcript.count("coasted past home") == 2


def test_a_turn_under_way_still_stops_at_home_once_the_menu_is_open(blaster):
    b = blaster
    b.attach_display()
    one_mode(b, "semi", device={"menuButtonHoldTime_ms": 1000, "pusherStallTime_ms": 2000},
             crank={"turnMs": 1900})
    b.press("trigger")
    assert b.run_until(lambda: b.peek("pusher")["state"] == "turning", 1000)
    b.release("trigger")
    b.hold("menu", 1100)
    assert b.peek("menuOpen")
    assert b.peek("pusher")["state"] == "turning"
    assert b.run_until(lambda: b.peek("pusher")["state"] == "parked", 2000)
    assert b.peek("menuOpen")
    assert b.peek("pusher")["home"]
    assert motor_runs(b)[-1][1] is not None


# ---- what the firmware refuses

def test_a_brushed_pusher_on_a_fet_is_refused_and_its_gate_held_off(blaster):
    b = blaster
    b.flash_preset("trifolium_v1_2", {"pusherType": "brushed_motor", "cycleSwitchPin": CYCLE_PIN})
    assert b.boot(2500)
    assert b.peek("pusherValid") is False
    assert b.peek("pusher") is None
    assert schema(b)["pinConflicts"] == [{"field": "pusher", "pin": 24,
                                          "against": "brushedNeedsEsc",
                                          "action": "pusherDisabled"}]
    b.press("select0")  # AUTO on the v1.2's default profile
    pull(b, 500)
    settle(b)
    gate = b.pin(24)
    assert gate["output"] and not gate["outputLevel"]
    assert not any(level for _, level in b.edges(24))


def test_a_brushed_pusher_with_no_cycle_switch_is_refused(blaster):
    b = blaster
    b.flash_preset("trifolium_v1_2", {"pusherType": "brushed_motor", "pusherDrive": "esc"})
    assert b.boot(2500)
    assert b.peek("pusherValid") is False
    assert schema(b)["pinConflicts"] == [{"field": "pusher", "pin": 255, "against": "noCycleSwitch",
                                          "action": "pusherDisabled"}]


def test_a_solenoid_has_no_crank_to_report(blaster):
    b = armed_v12(blaster, display=False)
    assert b.command("DUMP_MOTORS")["pusher"] is None
    assert b.command("DUMP_BOOT")["pusherHomeAtBoot"] is None


# ---- settings

BRUSHED_ROWS = ("Motor Voltage", "Turn Time", "Stall Time", "Cycle Debounce")
OTHER_ROWS = ("Reverse Direction", "Retract Time", "Vibration Pulse")


@pytest.mark.parametrize("pusher, brushed", [("brushed_motor", True), ("solenoid_openloop", False)])
def test_each_pusher_type_shows_its_own_rows(blaster, pusher, brushed):
    b = armed_v12(blaster, {**BRUSHED, "pusherType": pusher}, settle_ms=3000)
    open_menu(b)
    enter(b, "Advanced", "Solenoid / Pusher")
    listing = rows(b)
    assert [shown(listing, name) for name in BRUSHED_ROWS] == [brushed] * 4, listing
    assert [shown(listing, name) for name in OTHER_ROWS] == [not brushed] * 3, listing


def test_a_brushed_pusher_has_no_min_push(blaster):
    b = armed_v12(blaster, {**BRUSHED, **SENSING}, settle_ms=3000)
    open_menu(b)
    enter(b, "Advanced", "Dart Switch")
    listing = rows(b)
    assert shown(listing, "Dart Wait") and not shown(listing, "Min Push"), listing


@pytest.mark.parametrize("stored, loaded", [(2, "solenoid_openloop"), (1, "solenoid_openloop"),
                                            ("brushed_motor", "brushed_motor")])
def test_a_bare_2_from_before_2_1_still_loads_as_the_solenoid(blaster, stored, loaded):
    b = blaster
    b.flash_preset("trifolium_v1_2", {"pusherType": stored})
    assert b.boot(2500)
    assert b.wiring()["pusherType"] == loaded

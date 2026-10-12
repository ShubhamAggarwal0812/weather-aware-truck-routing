"""Driving time -> wall-clock time, with the FMCSA hours-of-service breaks.

A truck can't drive a 20-hour route in 20 hours, so checkpoint ETAs include the
two property-carrier rules that matter for a single trip:

* a 30-minute break once 8 hours have been driven since the last break, and
* a 10-hour off-duty rest once 11 hours have been driven since the last rest.

That gives a fixed cycle: drive 8h, break 30m, drive 3h, rest 10h. The driver is
assumed to start the trip fully rested. The 14-hour duty window is never hit by
this cycle (8h + 0.5h + 3h = 11.5h), and the 60/70-hour weekly limit is out of
scope because it depends on the driver's previous days.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

HOUR = 3600.0
DRIVE_BEFORE_BREAK_S = 8 * HOUR
BREAK_S = 0.5 * HOUR
MAX_DRIVE_S = 11 * HOUR
REST_S = 10 * HOUR
CYCLE_ELAPSED_S = MAX_DRIVE_S + BREAK_S + REST_S


@dataclass(frozen=True)
class Stop:
    kind: str  # "break" | "rest"
    drive_s: float  # driving time completed when the stop starts
    start_elapsed_s: float
    duration_s: float


def elapsed_s(drive_s: float, *, breaks: bool = True) -> float:
    """Wall-clock seconds since departure when ``drive_s`` of driving is done.

    A stop is only added once driving continues past its limit, so arriving
    exactly at the 11th hour doesn't pay for the rest that would follow.
    """
    if not breaks or drive_s <= 0:
        return max(0.0, drive_s)
    cycles = math.ceil(drive_s / MAX_DRIVE_S) - 1
    rem = drive_s - cycles * MAX_DRIVE_S
    return cycles * CYCLE_ELAPSED_S + rem + (BREAK_S if rem > DRIVE_BEFORE_BREAK_S else 0.0)


def drive_s_at(elapsed: float, *, breaks: bool = True) -> tuple[float, str]:
    """Inverse of :func:`elapsed_s`: driving done after ``elapsed`` seconds, and the activity."""
    if elapsed <= 0:
        return 0.0, "driving"
    if not breaks:
        return elapsed, "driving"
    cycles, rem = divmod(elapsed, CYCLE_ELAPSED_S)
    done = cycles * MAX_DRIVE_S
    if rem <= DRIVE_BEFORE_BREAK_S:
        return done + rem, "driving"
    if rem <= DRIVE_BEFORE_BREAK_S + BREAK_S:
        return done + DRIVE_BEFORE_BREAK_S, "break"
    if rem <= MAX_DRIVE_S + BREAK_S:
        return done + rem - BREAK_S, "driving"
    return done + MAX_DRIVE_S, "rest"


def stops(total_drive_s: float, *, breaks: bool = True) -> list[Stop]:
    """Every break and rest taken before the destination is reached."""
    if not breaks:
        return []
    out: list[Stop] = []
    cycle = 0
    while True:
        base_drive = cycle * MAX_DRIVE_S
        base_elapsed = cycle * CYCLE_ELAPSED_S
        if total_drive_s <= base_drive + DRIVE_BEFORE_BREAK_S:
            return out
        out.append(Stop("break", base_drive + DRIVE_BEFORE_BREAK_S, base_elapsed + DRIVE_BEFORE_BREAK_S, BREAK_S))
        if total_drive_s <= base_drive + MAX_DRIVE_S:
            return out
        out.append(Stop("rest", base_drive + MAX_DRIVE_S, base_elapsed + MAX_DRIVE_S + BREAK_S, REST_S))
        cycle += 1

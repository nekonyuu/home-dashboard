import { describe, expect, it } from "vitest";

import type { Schedule } from "../api/types";
import { formatMinute, groupDays, parisNow, segmentsOf } from "./schedule";

const SAME = [
  { minute: 240, setpoint: 21 },
  { minute: 360, setpoint: 20 },
  { minute: 1320, setpoint: 19 },
];

function schedule(days: Schedule["days"][number]["transitions"][]): Schedule {
  return {
    equipment: "room_1",
    mode: 1,
    mode_display: "PROG",
    days: days.map((transitions, weekday) => ({ weekday, transitions })),
    current_setpoint: null,
    applied_setpoint: null,
    next: null,
    override: null,
    updated_at: 0,
  };
}

describe("segmentsOf", () => {
  it("reporte la consigne de la veille avant le premier changement", () => {
    const days = Array(7).fill(SAME);
    expect(segmentsOf(days, 0)).toEqual([
      { start: 0, end: 240, setpoint: 19 },
      { start: 240, end: 360, setpoint: 21 },
      { start: 360, end: 1320, setpoint: 20 },
      { start: 1320, end: 1440, setpoint: 19 },
    ]);
  });

  it("une journée sans changement garde la consigne en cours", () => {
    const days = [[{ minute: 480, setpoint: 20 }], [], [], [], [], [], []];
    expect(segmentsOf(days, 3)).toEqual([{ start: 0, end: 1440, setpoint: 20 }]);
    expect(segmentsOf([[], [], [], [], [], [], []], 0)).toEqual([{ start: 0, end: 1440, setpoint: null }]);
  });
});

describe("groupDays", () => {
  it("regroupe une semaine identique", () => {
    const groups = groupDays(schedule(Array(7).fill(SAME)));
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("Tous les jours");
  });

  it("sépare semaine et week-end, et le lundi dont la nuit diffère", () => {
    const weekend = [{ minute: 480, setpoint: 21 }];
    const groups = groupDays(schedule([SAME, SAME, SAME, SAME, SAME, weekend, weekend]));
    expect(groups.map((g) => g.label)).toEqual(["Lun–Ven", "Sam–Dim"]);
    // lundi commence à 21 °C (reporté du dimanche), mardi à 19 °C : la tête de plage n'est pas affirmée
    expect(groups[0].segments[0]).toEqual({ start: 0, end: 240, setpoint: null });
    expect(groups[0].segments[3]).toEqual({ start: 1320, end: 1440, setpoint: 19 });
    expect(groups[1].segments[0]).toEqual({ start: 0, end: 480, setpoint: null });
  });
});

it("formatMinute et parisNow", () => {
  expect(formatMinute(0)).toBe("00:00");
  expect(formatMinute(1320)).toBe("22:00");
  // dimanche 25/10/2026 03:30 Paris = 02:30 UTC (après le passage à l'heure d'hiver)
  expect(parisNow(Date.UTC(2026, 9, 25, 2, 30))).toEqual({ weekday: 6, minute: 210 });
});

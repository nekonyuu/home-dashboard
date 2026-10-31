// Programme hebdomadaire du chauffage : regroupement des jours identiques et plages horaires.
import type { Schedule, ScheduleTransition } from "../api/types";

export const DAY_SHORT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
export const DAY_LONG = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];

export interface Segment {
  start: number; // minute incluse
  end: number; // minute exclue (1440 = minuit)
  setpoint: number | null; // null : aucune consigne connue
}

export interface DayGroup {
  weekdays: number[]; // jours consécutifs au programme identique (0 = lundi)
  label: string;
  transitions: ScheduleTransition[];
  segments: Segment[];
}

const sameDay = (a: ScheduleTransition[], b: ScheduleTransition[]) =>
  a.length === b.length && a.every((t, i) => t.minute === b[i].minute && t.setpoint === b[i].setpoint);

/** Consigne en vigueur à minuit : dernière transition des jours précédents. */
function carriedOver(days: ScheduleTransition[][], weekday: number): number | null {
  for (let back = 1; back <= 7; back++) {
    const day = days[(weekday - back + 7) % 7];
    if (day.length) return day[day.length - 1].setpoint;
  }
  return null;
}

export function segmentsOf(days: ScheduleTransition[][], weekday: number): Segment[] {
  const out: Segment[] = [];
  let current = carriedOver(days, weekday);
  let start = 0;
  for (const t of days[weekday]) {
    if (t.minute > start) out.push({ start, end: t.minute, setpoint: current });
    current = t.setpoint;
    start = t.minute;
  }
  out.push({ start, end: 1440, setpoint: current });
  // fusionne les plages contiguës de même consigne
  return out.reduce<Segment[]>((acc, s) => {
    const last = acc[acc.length - 1];
    if (last && last.setpoint === s.setpoint) last.end = s.end;
    else acc.push({ ...s });
    return acc;
  }, []);
}

function groupLabel(weekdays: number[]): string {
  if (weekdays.length === 7) return "Tous les jours";
  if (weekdays.length === 1) return DAY_LONG[weekdays[0]];
  return `${DAY_SHORT[weekdays[0]]}–${DAY_SHORT[weekdays[weekdays.length - 1]]}`;
}

/** Jours consécutifs (lundi -> dimanche) aux changements identiques.

La plage avant le premier changement dépend de la veille : si elle diffère entre les jours du groupe, sa consigne
est ``null`` (affichée « selon la veille ») plutôt qu'une valeur d'un seul des jours.
*/
export function groupDays(schedule: Schedule): DayGroup[] {
  const days = [...schedule.days].sort((a, b) => a.weekday - b.weekday).map((d) => d.transitions);
  const groups: DayGroup[] = [];
  days.forEach((transitions, weekday) => {
    const segments = segmentsOf(days, weekday);
    const last = groups[groups.length - 1];
    if (last && sameDay(last.transitions, transitions)) {
      last.weekdays.push(weekday);
      const head = last.segments[0];
      if (head.start === 0 && head.setpoint !== segments[0].setpoint) {
        head.setpoint = null;
        // la plage de tête ne fusionne plus avec la suivante
        if (head.end > (transitions[0]?.minute ?? 1440)) {
          last.segments = segmentsWithHead(transitions, null);
        }
      }
    } else {
      groups.push({ weekdays: [weekday], label: "", transitions, segments });
    }
  });
  for (const g of groups) g.label = groupLabel(g.weekdays);
  return groups;
}

function segmentsWithHead(transitions: ScheduleTransition[], head: number | null): Segment[] {
  const out: Segment[] = [];
  let current = head;
  let start = 0;
  for (const t of transitions) {
    if (t.minute > start) out.push({ start, end: t.minute, setpoint: current });
    current = t.setpoint;
    start = t.minute;
  }
  out.push({ start, end: 1440, setpoint: current });
  return out;
}

export function formatMinute(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

/** Jour de la semaine (0 = lundi) et minute courants, heure de Paris. */
export function parisNow(epochMs: number = Date.now()): { weekday: number; minute: number } {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Paris",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(epochMs));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const weekday = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].indexOf(get("weekday"));
  return { weekday, minute: Number(get("hour")) * 60 + Number(get("minute")) };
}

/** Intensité 0..1 d'une consigne entre les extrêmes du programme (teinte de remplissage). */
export function intensity(setpoint: number | null, min: number, max: number): number {
  if (setpoint === null) return 0;
  return max > min ? (setpoint - min) / (max - min) : 0.5;
}

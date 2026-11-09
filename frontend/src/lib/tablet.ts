import type { EnergyDay } from "../api/types";

export interface DayEnergy {
  day: string;
  heating: number;
  dhw: number;
  total: number;
  cost: number | null;
}

/**
 * Consommation du dernier jour pour lequel le fournisseur a publié des relevés (catégorie 1 = chauffage, 2 = eau chaude).
 * Le cloud publie avec retard : ce n'est pas forcément aujourd'hui, la tuile affiche la date.
 */
export function latestEnergyDay(days: EnergyDay[] | undefined): DayEnergy | null {
  if (!days?.length) return null;
  const day = days.reduce((m, d) => (d.day > m ? d.day : m), days[0].day);
  const rows = days.filter((d) => d.day === day);
  const heating = rows.filter((d) => d.category === 1).reduce((a, d) => a + d.kwh, 0);
  const dhw = rows.filter((d) => d.category === 2).reduce((a, d) => a + d.kwh, 0);
  const costs = rows.map((d) => d.cost);
  const cost = costs.every((c) => c === null) ? null : costs.reduce<number>((a, c) => a + (c ?? 0), 0);
  return { day, heating, dhw, total: rows.reduce((a, d) => a + d.kwh, 0), cost };
}

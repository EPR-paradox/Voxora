import { apiRequest, toQueryString } from "../../api/client";
import type { ScenarioDetail, ScenarioListResponse, ScenarioSummary } from "../../api/types";

export interface ScenarioFilters {
  category?: string | null;
  industry_segment?: string | null;
  role?: string | null;
  difficulty?: number | null;
  limit?: number;
  offset?: number;
}

export function listScenarios(filters: ScenarioFilters = {}): Promise<ScenarioListResponse> {
  const query = toQueryString({
    category: filters.category,
    industry_segment: filters.industry_segment,
    role: filters.role,
    difficulty: filters.difficulty,
    limit: filters.limit ?? 20,
    offset: filters.offset ?? 0,
  });
  return apiRequest<ScenarioListResponse>(`/scenarios${query}`);
}

export function getScenario(scenarioId: string): Promise<ScenarioDetail> {
  return apiRequest<ScenarioDetail>(`/scenarios/${scenarioId}`);
}

/** Distinct filter values present in the loaded page, for the filter chips. */
export function collectFilterValues(scenarios: ScenarioSummary[]) {
  const segments = new Set<string>();
  const roles = new Set<string>();
  for (const scenario of scenarios) {
    if (scenario.industry_segment) segments.add(scenario.industry_segment);
    for (const role of scenario.roles) roles.add(role);
  }
  return { segments: [...segments].sort(), roles: [...roles].sort() };
}

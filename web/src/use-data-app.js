import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { isTemporalField } from "./source-provenance.js";
import { validateMatchupRefresh } from "./content/dashboard/football.mjs";
import { validatePerformance } from "./content/performance/performance.mjs";

const queryUpdateProperties = {
  queryId: { type: "string" },
  rows: { type: "array", maxItems: 10_000, items: { type: "object" } },
  executedAt: { type: "string", format: "date-time", description: "When the source request finished, including timezone." },
};

const noVisibleReportFilters = [];
const noSubscribe = () => () => {};
const zeroVersion = () => 0;

export function listReviewedQueries(queries, queryMetadata) {
  return Object.entries(queries).map(([queryId, { rows, ...definition }]) => {
    const source = definition.source ?? {};
    const metadata = queryMetadata?.[queryId];
    return {
      ...definition, queryId,
      label: source.label, sql: source.sql, tables: source.tables ?? [],
      columns: Array.isArray(rows) ? [...new Set(rows.flatMap(Object.keys))] : metadata?.columns ?? [],
      rowCount: Array.isArray(rows) ? rows.length : metadata?.rowCount ?? 0,
      ...(queryMetadata ? { loaded: Array.isArray(rows) } : {}),
    };
  });
}

export function filterReviewedRows(rows, definitions, filters, queryId, breakdown = []) {
  let selectedRows = rows;
  const applicable = definitions.filter(({ queryIds }) => !Array.isArray(queryIds) || queryIds.includes(queryId));
  filters = Object.fromEntries(applicable.map(({ id, defaultValue, multiple }) => {
    const value = filters[id] ?? defaultValue ?? "all";
    return [id, multiple && Array.isArray(value) && value.length === 0 ? "all" : value];
  }));

  const latestFields = [];

  // Apply exact dimensions before choosing the latest available date in a range.
  const ordered = [...applicable].sort((a, b) =>
    Number(String(filters[a.id] ?? "").includes("..")) - Number(String(filters[b.id] ?? "").includes("..")));
  ordered.forEach(({ id, field, mode, operator, multiple }) => {
    if (filters[id] !== "all" && selectedRows.some((row) => Object.hasOwn(row, field))) {
      const selected = filters[id];
      if (multiple && Array.isArray(selected)) {
        const choices = new Set(selected);
        selectedRows = selectedRows.filter(row => choices.has(String(row[field])));
        return;
      }
      const ranged = typeof selected === "string" && selected.includes("..");
      const [start, end] = ranged ? selected.split("..") : [undefined, selected];
      const withinRange = selectedRows.filter((row) => String(row[field]) <= end
        && (!start || String(row[field]) >= start));
      if ((mode === "through" || operator === "lte") && breakdown.includes(field)) {
        selectedRows = withinRange;
      } else if (ranged) {
        selectedRows = withinRange;
        latestFields.push(field);
      } else {
        selectedRows = selectedRows.filter((row) => String(row[field]) === selected);
      }
    }
  });

  applicable.forEach(({ id, field }) => {
    if (filters[id] === "all" && breakdown.includes(field)
      && selectedRows.some((row) => String(row[field] ?? "").toLowerCase() === "all")
      && selectedRows.some((row) => Object.hasOwn(row, field)
        && String(row[field]).toLowerCase() !== "all")) {
      selectedRows = selectedRows.filter((row) => String(row[field]).toLowerCase() !== "all");
    }
  });

  applicable.forEach(({ id, field }) => {
    if (filters[id] === "all" && !breakdown.includes(field)
      && selectedRows.some((row) => String(row[field] ?? "").toLowerCase() === "all")) {
      selectedRows = selectedRows.filter((row) => String(row[field]).toLowerCase() === "all");
    }
  });

  // Select endpoints only after exact dimensions and aggregate-row preference.
  for (const field of latestFields) {
    const latest = selectedRows.reduce((last, row) => String(row[field]) > last ? String(row[field]) : last, "");
    selectedRows = selectedRows.filter((row) => String(row[field]) === latest);
  }
  return selectedRows;
}

// Resolve both scopes in one pass. Filtering already-collapsed global rows loses
// dimension detail; internal IDs also prevent page/section ID collisions.
export function resolveSectionRows(rows, pageDefinitions, pageValues, definitions, values, queryId, breakdown = [], {
  report = false, visibleFilterIds = [], periodField,
} = {}) {
  const combined = [...pageDefinitions.map((definition, index) => ({
    ...definition, id: `page:${index}`, value: pageValues[definition.id] ?? definition.defaultValue ?? "all",
    ...(report ? { visible: reportFilterVisible(definition, visibleFilterIds) } : {}),
  })), ...definitions.map((definition, index) => ({
    ...definition, id: `section:${index}`, value: values[definition.id] ?? definition.defaultValue ?? "all",
    ...(report ? { visible: true } : {}),
  }))];
  const selected = Object.fromEntries(combined.map(({ id, value }) => [id, value]));
  return report ? reportReviewedRows(rows, combined, selected, queryId, {
    breakdown, periodField: reportPeriodField(rows, pageDefinitions, queryId, periodField),
  })
    : filterReviewedRows(rows, combined, selected, queryId, breakdown);
}

export function previousPeriodRows(rows, definitions, filters, queryId, periodField, currentPeriod) {
  if (currentPeriod == null) return [];
  const comparisonFilters = { ...filters };
  definitions.forEach(({ id, field }) => {
    if (field === periodField) comparisonFilters[id] = "all";
  });
  const prior = filterReviewedRows(rows, definitions, comparisonFilters, queryId)
    .filter((row) => row[periodField] < currentPeriod);
  const previousPeriod = prior.reduce((latest, row) => (
    row[periodField] > latest ? row[periodField] : latest
  ), "");
  return prior.filter((row) => row[periodField] === previousPeriod);
}

export function reportFilterVisible(filter, visibleFilterIds = []) {
  return filter.visible === true || filter.reportVisible === true
    || filter.surface === "report" || (Array.isArray(filter.surfaces) && filter.surfaces.includes("report"))
    || (Array.isArray(visibleFilterIds) && visibleFilterIds.includes(filter.id));
}

// Prefer explicit reporting metadata; ambiguous temporal columns are not a basis
// for inventing a latest/prior comparison.
export function reportPeriodField(rows, definitions, queryId, requestedField) {
  const columns = [...new Set(rows.flatMap(Object.keys))];
  if (requestedField) return columns.includes(requestedField) ? requestedField : undefined;
  const defined = [...new Set(definitions.filter(({ field, type, valueType, queryIds }) =>
    (!Array.isArray(queryIds) || queryIds.includes(queryId))
    && columns.includes(field) && isTemporalField(field, type ?? valueType)).map(({ field }) => field))];
  if (defined.length) return defined.length === 1 ? defined[0] : undefined;
  const inferred = columns.filter((field) => isTemporalField(field));
  return inferred.length === 1 ? inferred[0] : undefined;
}

function compareReportPeriods(left, right) {
  return String(left).localeCompare(String(right), undefined, { numeric: true });
}

// History respects visible report filters. Latest selects a reviewed period in that
// scope; previous clears only its reporting-field filters and keeps the same grain.
// With no unambiguous reporting field, history is available but comparisons are empty.
export function reportReviewedRows(rows, definitions, filters, queryId, {
  period = "history", periodField, currentPeriod, breakdown = [], visibleFilterIds = [],
} = {}) {
  if (!["history", "latest", "previous"].includes(period)) {
    throw new Error(`Unknown report reviewed-data period: ${period}`);
  }
  const field = reportPeriodField(rows, definitions, queryId, periodField);
  const values = Object.fromEntries(definitions.map((definition) => [definition.id,
    reportFilterVisible(definition, visibleFilterIds) ? filters[definition.id] ?? "all" : "all"]));
  const scopedBreakdown = [...new Set([...breakdown, ...(field ? [field] : [])])];
  // Report history retains every reviewed period inside a visible range. The shared
  // dashboard filter keeps its own latest-endpoint behavior unchanged.
  const scopedDefinitions = definitions.map((definition) => definition.field === field
    && typeof values[definition.id] === "string" && values[definition.id].includes("..")
    ? { ...definition, mode: "through" } : definition);
  const scoped = filterReviewedRows(rows, scopedDefinitions, values, queryId, scopedBreakdown);
  if (period === "history") return scoped;
  if (!field) return [];

  const periods = [...new Set(scoped.map((row) => row[field]).filter((value) => value != null))]
    .sort(compareReportPeriods);
  const selected = currentPeriod ?? periods.at(-1);
  if (selected == null) return [];
  if (period === "latest") return scoped.filter((row) => compareReportPeriods(row[field], selected) === 0);

  // A selected date or narrow range must not erase the preceding comparison period.
  // Keep every other visible dimension, query scope, and aggregate/breakdown choice.
  const comparisonValues = { ...values };
  definitions.forEach((definition) => {
    if (definition.field === field) comparisonValues[definition.id] = "all";
  });
  const candidates = filterReviewedRows(rows, definitions, comparisonValues, queryId, scopedBreakdown)
    .filter((row) => row[field] != null && compareReportPeriods(row[field], selected) < 0);
  const previous = candidates.map((row) => row[field]).sort(compareReportPeriods).at(-1);
  return previous == null ? [] : candidates.filter((row) => compareReportPeriods(row[field], previous) === 0);
}

export function reportAggregateRows(rows, definitions, filters, queryId, options = {}) {
  // Suppress breakdown rows without discarding an explicitly selected dimension.
  return reportReviewedRows(rows, definitions, filters, queryId, { ...options, breakdown: [] });
}

export function useDataApp(snapshot, {
  hosted = false,
  canEdit = true,
  onSnapshotChange,
  queryDataStore,
  initialFilters = {},
  authoritativeInitialFilters = {},
  filterDefinitions = snapshot.filters ?? [],
  visibleFilterIds = noVisibleReportFilters,
} = {}) {
  const [localQueries, setQueries] = useState(snapshot.queries);
  useSyncExternalStore(queryDataStore?.subscribe ?? noSubscribe, queryDataStore?.getVersion ?? zeroVersion,
    queryDataStore?.getVersion ?? zeroVersion);
  const queries = queryDataStore ? queryDataStore.getQueries() : localQueries;
  const queriesRef = useRef(snapshot.queries);
  queriesRef.current = queries;
  const refreshPending = useRef(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState(null);
  // User-requested NFL extension for separately hosted, same-origin score feeds.
  // Native Sites loading, data inspection and presentation state are retained.
  useEffect(() => {
    const config = snapshot.extensions?.nflLiveFeed;
    if (hosted || !config?.endpoint) return;
    const performance = new URL(window.location.href).searchParams.get("page") === "performance";
    const endpoint = new URL(performance ? "./performance.json" : config.endpoint, window.location.href);
    if (endpoint.origin !== window.location.origin) return;
    const requestedWeek = Number(new URL(window.location.href).searchParams.get("week") || snapshot.period?.week);
    const week = Number.isInteger(requestedWeek) && requestedWeek >= 1 && requestedWeek <= 18 ? requestedWeek : snapshot.period?.week;
    endpoint.searchParams.set("week", String(week));
    let active = true;
    let inFlight = null;
    let sourceTime = week === snapshot.period?.week ? Date.parse(snapshot.generatedAt || 0) : 0;
    const load = async (event) => {
      if (!active || inFlight || document.hidden) return;
      const controller = new AbortController();
      inFlight = controller;
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const requestUrl = new URL(endpoint);
        if (event?.type === "nfl:refresh-scores") requestUrl.searchParams.set("refresh", "1");
        const response = await fetch(requestUrl, { cache: "no-store", credentials: "same-origin", signal: controller.signal });
        if (!response.ok) throw new Error("Score feed is unavailable. Showing the last successful update.");
        const next = await response.json();
        if (performance) {
          validatePerformance(next, snapshot.period?.season);
          const nextTime = Date.parse(next.generatedAt);
          if (nextTime < sourceTime) throw new Error("Performance feed is older than the displayed analysis.");
          if (!active) return;
          sourceTime = nextTime;
          const performanceQueries = Object.fromEntries(Object.entries(next.queries).filter(([key]) => key.startsWith("performance-")));
          const nextQueries = { ...queriesRef.current, ...performanceQueries };
          queriesRef.current = nextQueries;
          setQueries(nextQueries);
          onSnapshotChange?.(current => ({ ...current, queries: nextQueries, generatedAt: next.generatedAt,
            nflFeed: { status: "connected", lastSuccessfulSourceAt: next.queries["performance-picks"].source.executedAt, error: null } }));
          return;
        }
        const query = next.queries?.matchups;
        if (next.period?.season !== snapshot.period?.season || next.period?.week !== week || !Array.isArray(query?.rows))
          throw new Error("Score feed returned a different week or an invalid payload.");
        const ids = query.rows.map(row => row.eventId);
        if (!ids.length || new Set(ids).size !== ids.length || query.rows.some(row => !row.homeCode || !row.awayCode))
          throw new Error("Score feed has missing or duplicated games.");
        const expected = week === snapshot.period?.week ? queriesRef.current.matchups?.rows : snapshot.seasonSchedule?.[String(week)];
        validateMatchupRefresh(expected, query.rows);
        const nextTime = Date.parse(next.generatedAt);
        if (!Number.isFinite(nextTime) || nextTime < sourceTime)
          throw new Error("Score feed is older than the displayed data.");
        if (!active) return;
        const brochure = next.queries?.brochure;
        if (brochure && (!Array.isArray(brochure.rows) || brochure.rows.some(row => !ids.includes(row.eventId))))
          throw new Error("Brochure feed does not match this week's games.");
        sourceTime = nextTime;
        const nextQueries = { ...queriesRef.current, matchups: query, ...(brochure ? {brochure} : {}) };
        queriesRef.current = nextQueries;
        setQueries(nextQueries);
        onSnapshotChange?.(current => ({ ...current, queries: nextQueries, period: next.period, generatedAt: next.generatedAt,
          nflFeed: { status: "connected", lastSuccessfulSourceAt: next.generatedAt, error: null } }));
      } catch (error) {
        if (active) onSnapshotChange?.(current => ({ ...current,
          nflFeed: { ...(current.nflFeed || {}), status: "unavailable", error: error.message } }));
      } finally {
        clearTimeout(timeout);
        inFlight = null;
      }
    };
    const interval = setInterval(load, Math.max(15000, Math.min(300000, config.intervalMs || 60000)));
    const visible = () => { if (!document.hidden) void load(); };
    window.addEventListener("nfl:refresh-scores", load);
    document.addEventListener("visibilitychange", visible);
    void load();
    return () => {
      active = false;
      clearInterval(interval);
      inFlight?.abort();
      window.removeEventListener("nfl:refresh-scores", load);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [hosted, snapshot.extensions?.nflLiveFeed?.endpoint, snapshot.extensions?.nflLiveFeed?.intervalMs,
    snapshot.period?.season, snapshot.period?.week, onSnapshotChange]);
  const refresh = useCallback(() => {
    if (!hosted || !queryDataStore?.live || snapshot.refresh !== "live") return Promise.reject(new Error("Live refresh is unavailable."));
    if (refreshPending.current) return refreshPending.current;
    setRefreshing(true);
    setRefreshError(null);
    const operation = queryDataStore.refresh();
    refreshPending.current = operation.catch(error => {
      setRefreshError(error);
      throw error;
    }).finally(() => {
      refreshPending.current = null;
      setRefreshing(false);
    });
    return refreshPending.current;
  }, [hosted, snapshot.refresh, queryDataStore, onSnapshotChange]);
  const [filters, setFilters] = useState(() => Object.fromEntries(
    (snapshot.filters ?? []).map(({ id, defaultValue }) => [id,
      initialFilters[id] === "all" && defaultValue && defaultValue !== "all"
        && !Object.hasOwn(authoritativeInitialFilters, id)
        ? defaultValue : initialFilters[id] ?? defaultValue ?? "all"]),
  ));

  useEffect(() => {
    if (!hosted || !canEdit) return;
    const context = document.modelContext ?? navigator.modelContext;
    if (typeof context?.registerTool !== "function") return;

    const tools = [{
      name: "list_data_app_queries",
      description: "List reviewed Data app queries, provenance, columns, and row counts.",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true, untrustedContentHint: true },
      execute: async () => listReviewedQueries(queriesRef.current,
        queryDataStore ? snapshot._dataAppQueryLoading?.queries ?? {} : undefined),
    }, {
      name: "update_data_app_query",
      description: "Update reviewed Data app rows and source execution times. Use updates to commit every dataset in a refresh together.",
      inputSchema: {
        type: "object",
        oneOf: [{
          properties: queryUpdateProperties,
          required: ["queryId", "rows"], additionalProperties: false,
        }, {
          properties: { updates: {
            type: "array", minItems: 1, maxItems: 100,
            items: { type: "object", properties: queryUpdateProperties,
              required: ["queryId", "rows", "executedAt"], additionalProperties: false },
          } },
          required: ["updates"], additionalProperties: false,
        }],
      },
      execute: async (input) => {
        const batch = Object.hasOwn(input, "updates");
        // Owner edits retain the complete-data behavior, including palette and
        // source metadata. A failed load must not turn an edit into partial data.
        await queryDataStore?.loadAll();
        const response = await fetch(batch ? "/api/queries" : `/api/queries/${encodeURIComponent(input.queryId)}`, {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(batch ? input : { rows: input.rows, executedAt: input.executedAt }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Unable to update Data app data.");
        const updates = batch ? result.updates : [result];
        queriesRef.current = { ...(queryDataStore?.getQueries() ?? queriesRef.current) };
        for (const { queryId, rows, executedAt } of updates) {
          const query = queriesRef.current[queryId];
          queriesRef.current[queryId] = { ...query, rows,
            source: { ...query.source, ...(executedAt === undefined ? {} : { executedAt }) } };
          queryDataStore?.replace(queryId, rows, executedAt);
        }
        queriesRef.current = queryDataStore?.getQueries() ?? queriesRef.current;
        setQueries(queriesRef.current);
        const nextQueries = queriesRef.current;
        onSnapshotChange?.((current) => ({
          ...current, generatedAt: result.generatedAt, queries: nextQueries,
          ...(queryDataStore ? { _dataAppQueryLoading: undefined } : {}),
        }));
        const counts = updates.map(({ queryId, rows }) => ({ queryId, rowCount: rows.length }));
        return batch ? { updates: counts } : counts[0];
      },
    }];

    const enabledTools = tools.filter(tool => snapshot.dataMode !== "live" || tool.name !== "update_data_app_query");
    enabledTools.forEach((tool) => {
      const report = (error) => console.error(`Unable to register Data app tool ${tool.name}.`, error);
      try {
        Promise.resolve(context.registerTool(tool)).catch(report);
      } catch (error) {
        report(error);
      }
    });
    return () => enabledTools.forEach((tool) => context.unregisterTool?.(tool.name));
  }, [canEdit, hosted, onSnapshotChange, snapshot, queryDataStore]);

  const setFilter = useCallback((id, value) => {
    setFilters((current) => ({ ...current, [id]: value }));
  }, []);

  const replaceFilters = useCallback((values) => {
    setFilters((current) => {
      const next = Object.fromEntries((snapshot.filters ?? []).map(({ id, defaultValue }) =>
        [id, values[id] ?? defaultValue ?? "all"]));
      return Object.keys(next).length === Object.keys(current).length
        && Object.entries(next).every(([id, value]) => current[id] === value) ? current : next;
    });
  }, [snapshot.filters]);

  const report = snapshot.surface === "report";
  const reviewedRows = useCallback((queryId, breakdown = []) => {
    const rows = queries[queryId]?.rows ?? [];
    if (report) return reportReviewedRows(rows, snapshot.filters ?? [], filters, queryId, {
      periodField: queries[queryId]?.reportingField, breakdown, visibleFilterIds,
    });
    return filterReviewedRows(rows, filterDefinitions, filters, queryId, breakdown);
  }, [filters, queries, report, snapshot, visibleFilterIds, filterDefinitions]);

  const reviewedPeriodRows = useCallback((queryId, options = {}) => reportReviewedRows(
    queries[queryId]?.rows ?? [], snapshot.filters ?? [], filters, queryId,
    { periodField: queries[queryId]?.reportingField, visibleFilterIds, ...options },
  ), [filters, queries, snapshot, visibleFilterIds]);

  const reviewedAggregatePeriodRows = useCallback((queryId, options = {}) => reportAggregateRows(
    queries[queryId]?.rows ?? [], snapshot.filters ?? [], filters, queryId,
    { periodField: queries[queryId]?.reportingField, visibleFilterIds, ...options },
  ), [filters, queries, snapshot, visibleFilterIds]);

  const activeFilters = filterDefinitions
    .filter(filter => !report || reportFilterVisible(filter, visibleFilterIds))
    .filter(({ id }) => filters[id] != null && filters[id] !== "all"
      && (!Array.isArray(filters[id]) || filters[id].length > 0))
    .map(({ id, field, label, queryIds }) => ({
      field, label, value: typeof filters[id] === "string"
        ? filters[id].replace("..", " – ") : filters[id],
      ...(Array.isArray(queryIds) ? { queryIds } : {}),
    }));

  return {
    queries, filters, setFilter, replaceFilters, reviewedRows, reviewedPeriodRows, refresh, refreshing,
    refreshError: queryDataStore?.live ? queryDataStore.error(Object.keys(queries)) : refreshError,
    reviewedAggregatePeriodRows, activeFilters,
  };
}

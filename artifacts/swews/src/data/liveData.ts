/**
 * Backward-compatible re-export shim.
 *
 * The real data hooks now live in `useSpaceWeatherData.ts` and are backed by
 * TanStack Query (single source of fetched truth, automatic deduplication
 * across components). Old import paths continue to work; new code should
 * import directly from `useSpaceWeatherData`.
 */
export * from "./useSpaceWeatherData";

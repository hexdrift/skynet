/**
 * Sidebar feature — public API.
 *
 * Currently exposes only the pure helpers extracted from
 * `src/components/sidebar.tsx`. The JSX render body stays in the
 * component file.
 */
export { matchesJobSearch, groupJobsByRecency, type JobGroup } from "./lib/group-jobs";

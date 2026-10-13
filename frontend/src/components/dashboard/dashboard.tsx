"use client";

import Link from "next/link";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { useApiResource } from "@/hooks/use-api-resource";
import { api } from "@/lib/api";
import type { Stats } from "@/lib/api/types";
import { useEnums } from "@/providers/enum-provider";
import { CountGroup, type CountEntry } from "./count-group";
import styles from "./dashboard.module.css";
import { RecentRuns } from "./recent-runs";

const RECENT_RUN_LIMIT = 10;

function loadDashboard() {
  return Promise.all([api.stats(), api.listRuns({ limit: RECENT_RUN_LIMIT })]);
}

/** Entries in enum order; a code that the stats carry but the enums lack is appended. */
function entriesFor(
  enumName: string,
  counts: Record<string, number>,
  enums: ReturnType<typeof useEnums>,
): CountEntry[] {
  const listed = enums.values(enumName).map((item) => ({
    code: item.code,
    label: item.label,
    count: counts[item.code] ?? 0,
  }));
  const known = new Set(listed.map((entry) => entry.code));
  const extra = Object.keys(counts)
    .filter((code) => !known.has(code))
    .map((code) => ({ code, label: code, count: counts[code] }));
  return [...listed, ...extra];
}

function Counts({ stats }: { stats: Stats }) {
  const enums = useEnums();
  return (
    <>
      <p className={styles.total}>
        Total bugs: <strong>{stats.total}</strong>
      </p>
      <div className={styles.groups}>
        <CountGroup title="By status" entries={entriesFor("BugStatus", stats.by_status, enums)} />
        <CountGroup title="By component" entries={entriesFor("Component", stats.by_component, enums)} />
        <CountGroup title="By severity" entries={entriesFor("Severity", stats.by_severity, enums)} />
      </div>
    </>
  );
}

export function Dashboard() {
  const enums = useEnums();
  const resource = useApiResource(loadDashboard);
  const failure = resource.error ?? enums.error;

  const retry = () => {
    if (enums.status === "error") enums.retry();
    if (resource.status === "error") resource.reload();
  };

  let body;
  if (failure !== null) {
    body = <ErrorState message={failure.message} onRetry={retry} />;
  } else if (resource.status !== "success" || enums.status !== "ready") {
    body = <LoadingState />;
  } else {
    const [stats, runs] = resource.data;
    body = (
      <>
        {stats.total === 0 ? (
          <EmptyState>
            No bugs yet. Go to <Link href="/operations">Operations</Link> to initialize and seed the database.
          </EmptyState>
        ) : (
          <Counts stats={stats} />
        )}
        <RecentRuns runs={runs.items} />
      </>
    );
  }

  return (
    <div className="page">
      <h1>Dashboard</h1>
      {body}
    </div>
  );
}

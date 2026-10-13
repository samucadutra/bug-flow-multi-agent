import Link from "next/link";
import { EmptyState } from "@/components/states/empty-state";
import type { Run } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";
import { useEnums } from "@/providers/enum-provider";
import styles from "./dashboard.module.css";

export function RecentRuns({ runs }: { runs: Run[] }) {
  const enums = useEnums();
  return (
    <section aria-labelledby="recent-runs-heading">
      <h2 id="recent-runs-heading">Recent runs</h2>
      {runs.length === 0 ? (
        <EmptyState>No runs yet.</EmptyState>
      ) : (
        <ul className={styles.runs}>
          {runs.map((run) => (
            <li key={run.id} className={styles.run} data-run-id={run.id}>
              <Link href={`/runs/${run.id}`}>Run {run.id}</Link>
              <span>{enums.label("RunType", run.type)}</span>
              <span>{enums.label("RunStatus", run.status)}</span>
              <span>{formatDuration(run.started_at, run.finished_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

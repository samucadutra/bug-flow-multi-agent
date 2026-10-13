const EMPTY = "—";

/** Whole seconds between start and finish as "<n> s" or "<m> m <s> s"; a missing finish is a dash. */
export function formatDuration(startedAt: string, finishedAt: string | null): string {
  if (finishedAt === null) return EMPTY;
  const started = Date.parse(startedAt);
  const finished = Date.parse(finishedAt);
  if (Number.isNaN(started) || Number.isNaN(finished)) return EMPTY;
  const seconds = Math.max(0, Math.floor((finished - started) / 1000));
  if (seconds < 60) return `${seconds} s`;
  return `${Math.floor(seconds / 60)} m ${seconds % 60} s`;
}

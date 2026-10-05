/**
 * Unit of Work — opt-in interface for atomic multi-aggregate writes.
 *
 * Single-write use cases do not need this. Inject only when an operation
 * writes to two or more aggregates that must commit together.
 *
 * See references/composition-root.md (section 3) for the implementation
 * mechanism (AsyncLocalStorage transaction context) and the per-ORM adapter.
 */
export interface UnitOfWork {
  run<T>(work: () => Promise<T>): Promise<T>;
}

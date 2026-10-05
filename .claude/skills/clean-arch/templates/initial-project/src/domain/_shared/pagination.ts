/**
 * Pagination contract used by List/Search use cases.
 *
 * Read endpoints — and only read endpoints — accept PageInput in their input
 * and return PageOutput<T> in their output. The implementation in
 * infra/queries/<feature>/ is responsible for translating page+pageSize
 * into the underlying ORM call.
 */
export type PageInput = {
  /** 1-based. */
  page: number;
  /** Bounded by the implementation; recommended max 100. */
  pageSize: number;
};

export type PageOutput<T> = {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
};

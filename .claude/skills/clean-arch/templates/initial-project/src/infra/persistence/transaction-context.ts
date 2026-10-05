import { AsyncLocalStorage } from 'node:async_hooks';

/**
 * Transaction context — carries the current transaction client across
 * async calls without threading it through every function signature.
 *
 * Used by Repository implementations: each repo method routes its DB call
 * through `currentClient(this.<defaultClient>)`. When inside a UoW, the
 * AsyncLocalStorage returns the active transaction; outside, it returns
 * the fallback (the regular client).
 *
 * This template uses `unknown` for the client type — replace with the
 * actual ORM client / transaction client type for your project (e.g.,
 * `PrismaClient | Prisma.TransactionClient` for Prisma).
 */

const storage = new AsyncLocalStorage<unknown>();

export const withTransaction = async <T>(client: unknown, fn: () => Promise<T>): Promise<T> =>
  storage.run(client, fn);

export const currentClient = <T>(fallback: T): T => (storage.getStore() as T | undefined) ?? fallback;

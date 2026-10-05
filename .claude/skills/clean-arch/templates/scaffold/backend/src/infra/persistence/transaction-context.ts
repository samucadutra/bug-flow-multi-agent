import { AsyncLocalStorage } from "node:async_hooks";

const storage = new AsyncLocalStorage<unknown>();

export function currentTransaction<T>(fallback: T): T {
  return (storage.getStore() as T | undefined) ?? fallback;
}

export async function runInTransaction<T>(client: unknown, work: () => Promise<T>): Promise<T> {
  return storage.run(client, work);
}

"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useApiResource } from "@/hooks/use-api-resource";
import { api } from "@/lib/api";
import type { ApiClient } from "@/lib/api";
import type { ApiError } from "@/lib/api/errors";
import type { EnumValue } from "@/lib/api/types";

export interface EnumsContextValue {
  status: "loading" | "ready" | "error";
  error: ApiError | null;
  /** Label for a code; an unknown code or enum returns the code itself. */
  label: (enumName: string, code: string) => string;
  /** Values of an enum in the order served; empty when unknown or not loaded. */
  values: (enumName: string) => EnumValue[];
  retry: () => void;
}

const EnumsContext = createContext<EnumsContextValue | null>(null);

export function EnumProvider({ children, client = api }: { children: ReactNode; client?: ApiClient }) {
  const load = useCallback(() => client.enums(), [client]);
  const resource = useApiResource(load);

  const byName = useMemo(() => {
    const map = new Map<string, EnumValue[]>();
    if (resource.status === "success") {
      for (const entry of resource.data.enums) map.set(entry.name, entry.values);
    }
    return map;
  }, [resource.status, resource.data]);

  const value = useMemo<EnumsContextValue>(
    () => ({
      status: resource.status === "success" ? "ready" : resource.status,
      error: resource.error,
      label: (enumName, code) => byName.get(enumName)?.find((item) => item.code === code)?.label ?? code,
      values: (enumName) => byName.get(enumName) ?? [],
      retry: resource.reload,
    }),
    [byName, resource.status, resource.error, resource.reload],
  );

  return <EnumsContext.Provider value={value}>{children}</EnumsContext.Provider>;
}

export function useEnums(): EnumsContextValue {
  const context = useContext(EnumsContext);
  if (context === null) throw new Error("useEnums must be used inside EnumProvider");
  return context;
}

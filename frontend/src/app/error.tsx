"use client";

import { ErrorState } from "@/components/states/error-state";

export default function ErrorBoundary({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="page">
      <h1>Something went wrong</h1>
      <ErrorState message="An unexpected error occurred while showing this page." onRetry={reset} />
    </div>
  );
}

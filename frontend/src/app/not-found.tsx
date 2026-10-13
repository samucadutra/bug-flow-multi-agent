import Link from "next/link";
import { EmptyState } from "@/components/states/empty-state";

export default function NotFound() {
  return (
    <div className="page">
      <h1>Page not found</h1>
      <EmptyState action={<Link href="/">Back to the Dashboard</Link>}>
        The page you asked for was not found.
      </EmptyState>
    </div>
  );
}

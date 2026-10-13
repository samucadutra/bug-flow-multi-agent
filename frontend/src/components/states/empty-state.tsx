import type { ReactNode } from "react";
import styles from "./states.module.css";

export interface EmptyStateProps {
  children: ReactNode;
  /** Optional call to action rendered under the message. */
  action?: ReactNode;
}

export function EmptyState({ children, action }: EmptyStateProps) {
  return (
    <div className={styles.empty}>
      <p className={styles.message}>{children}</p>
      {action ? <div>{action}</div> : null}
    </div>
  );
}

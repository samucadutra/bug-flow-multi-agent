import styles from "./states.module.css";

export interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className={styles.error}>
      <p className={styles.message}>{message}</p>
      {onRetry ? (
        <button type="button" className={styles.button} onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

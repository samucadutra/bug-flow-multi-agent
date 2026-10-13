import styles from "./states.module.css";

export function LoadingState() {
  return (
    <div role="status" className={styles.loading}>
      Loading
    </div>
  );
}

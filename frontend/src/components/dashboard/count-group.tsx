import styles from "./dashboard.module.css";

export interface CountEntry {
  code: string;
  label: string;
  count: number;
}

export interface CountGroupProps {
  title: string;
  entries: CountEntry[];
}

/** Entries are expected in enum order, including zero counts. */
export function CountGroup({ title, entries }: CountGroupProps) {
  const headingId = `group-${title.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <section className={styles.group} aria-labelledby={headingId}>
      <h2 id={headingId}>{title}</h2>
      <ul className={styles.entries}>
        {entries.map((entry) => (
          <li key={entry.code} className={styles.entry}>
            <span>{entry.label}</span>
            <span className={styles.count}>{entry.count}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

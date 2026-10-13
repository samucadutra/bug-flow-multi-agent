import Link from "next/link";
import type { ReactNode } from "react";
import { MainNav } from "./main-nav";
import styles from "./shell.module.css";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <>
      <header className={styles.header}>
        <div className={styles.bar}>
          <Link href="/" className={styles.brand}>
            BugFlow
          </Link>
          <MainNav />
        </div>
      </header>
      <main className={styles.main}>{children}</main>
    </>
  );
}

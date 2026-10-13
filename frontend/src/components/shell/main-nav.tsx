"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import styles from "./shell.module.css";

const ITEMS = [
  { href: "/", name: "Dashboard" },
  { href: "/bugs", name: "Bugs" },
  { href: "/search", name: "Search" },
  { href: "/operations", name: "Operations" },
] as const;

function isCurrent(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export function MainNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <nav aria-label="Primary" className={styles.nav}>
      <button
        type="button"
        className={styles.menuButton}
        aria-expanded={open}
        aria-controls="primary-links"
        onClick={() => setOpen((value) => !value)}
      >
        Menu
      </button>
      <ul id="primary-links" className={styles.links} data-open={open}>
        {ITEMS.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className={styles.link}
              aria-current={isCurrent(pathname, item.href) ? "page" : undefined}
              onClick={() => setOpen(false)}
            >
              {item.name}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

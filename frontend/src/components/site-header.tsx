"use client";

import { LineChart, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";

import { StockSearch } from "@/components/stock-search";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Piyasa" },
  { href: "/karsilastir", label: "Karşılaştır" },
  { href: "/favoriler", label: "Favoriler" },
  { href: "/portfoy", label: "Portföy" },
  { href: "/alarmlar", label: "Alarmlar" },
];

export function SiteHeader() {
  const path = usePathname();
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <LineChart className="size-5 text-primary" />
          <span className="hidden sm:inline">BIST Intelligence</span>
        </Link>
        <nav className="hidden items-center gap-1 md:flex">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "rounded-md px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground",
                (n.href === "/" ? path === "/" : path.startsWith(n.href)) && "bg-muted text-foreground",
              )}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <StockSearch className="ml-auto w-full max-w-xs" />
        <Button
          variant="ghost"
          size="icon"
          aria-label="Temayı değiştir"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
          <Sun className="hidden dark:block" />
          <Moon className="dark:hidden" />
        </Button>
      </div>
      <nav className="flex gap-1 overflow-x-auto border-t px-4 py-1 md:hidden">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} className="shrink-0 rounded-md px-2 py-1 text-sm text-muted-foreground">
            {n.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}

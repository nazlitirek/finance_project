"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Hit = { symbol: string; name: string; sector: string | null; instrument_type: string };

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** Hisse kodu veya şirket adıyla arama. onSelect verilmezse hisse sayfasına gider. */
export function StockSearch({
  onSelect,
  placeholder = "Hisse kodu veya şirket adı…",
  className,
}: {
  onSelect?: (hit: Hit) => void;
  placeholder?: string;
  className?: string;
}) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const term = useDebounced(q.trim(), 150);
  const { data, isLoading, error } = useSWR<Hit[]>(term ? `/stocks/search?q=${encodeURIComponent(term)}&limit=10` : null);
  const hits = data ?? [];

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function choose(h: Hit) {
    setOpen(false);
    setQ("");
    if (onSelect) onSelect(h);
    else router.push(`/hisse/${h.symbol}`);
  }

  return (
    <div ref={box} className={cn("relative", className)}>
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={q}
        placeholder={placeholder}
        aria-label="Hisse ara"
        className="pl-8"
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (!hits.length) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, hits.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            choose(hits[active]);
          } else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && term && (
        <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-lg">
          {error && <p className="p-3 text-sm text-destructive">{error.message}</p>}
          {isLoading && !data && <p className="p-3 text-sm text-muted-foreground">Aranıyor…</p>}
          {data && hits.length === 0 && <p className="p-3 text-sm text-muted-foreground">Sonuç bulunamadı.</p>}
          {hits.map((h, i) => (
            <button
              key={h.symbol}
              type="button"
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(h)}
              className={cn(
                "flex w-full items-baseline gap-2 px-3 py-2 text-left text-sm",
                i === active && "bg-muted",
              )}
            >
              <span className="w-16 shrink-0 font-mono font-semibold">{h.symbol}</span>
              <span className="truncate">{h.name}</span>
              {h.instrument_type === "index" && <span className="ml-auto text-xs text-muted-foreground">Endeks</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

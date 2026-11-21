"use client";

import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { LabelBadge, Notes, ScoreValue } from "@/components/common";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { byUnit, isNum, MODULE_TR, num, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

import type { Metric, ModuleResult } from "./types";

export function SignalIcon({ signal }: { signal?: string | null }) {
  if (signal === "positive") return <ArrowUpRight className="size-4 text-emerald-500" aria-label="olumlu" />;
  if (signal === "negative") return <ArrowDownRight className="size-4 text-red-500" aria-label="olumsuz" />;
  if (signal === "neutral") return <Minus className="size-4 text-muted-foreground" aria-label="nötr" />;
  return null;
}

/** Modül başlığı: puan, anlam, güvenilirlik, alt kategori puanları */
export function ModuleHeader({ m, componentNames }: { m: ModuleResult; componentNames?: Record<string, string> }) {
  const comps = Object.entries(m.components ?? {});
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <ScoreValue score={m.score} className="text-3xl" />
        <LabelBadge label={m.label} />
        <span className="text-sm text-muted-foreground">
          Güvenilirlik: {pct(m.reliability, 0)}
          {m.as_of ? ` · Veri tarihi: ${m.as_of}` : ""}
        </span>
      </div>
      <p className="text-sm text-muted-foreground">{m.meaning}</p>
      {comps.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {comps.map(([k, v]) => (
            <div key={k} className="rounded-lg border p-2">
              <div className="text-xs text-muted-foreground">{componentNames?.[k] ?? k}</div>
              <ScoreValue score={v} className="text-lg" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function MetricTable({ metrics, showSector = false }: { metrics: Metric[]; showSector?: boolean }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Gösterge</TableHead>
          <TableHead className="text-right">Değer</TableHead>
          <TableHead className="text-right">Önceki</TableHead>
          {showSector && <TableHead className="text-right">Sektör medyanı</TableHead>}
          <TableHead>Yorum</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {metrics.map((m) => (
          <TableRow key={m.code}>
            <TableCell>
              {m.formula ? (
                <Tooltip>
                  <TooltipTrigger className="cursor-help text-left underline decoration-dotted underline-offset-4">
                    {m.name}
                  </TooltipTrigger>
                  <TooltipContent className="max-w-sm">{m.formula}</TooltipContent>
                </Tooltip>
              ) : (
                m.name
              )}
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums">
              <span className="inline-flex items-center gap-1">
                <SignalIcon signal={m.signal} />
                {byUnit(m.value, m.unit)}
              </span>
            </TableCell>
            <TableCell className="text-right font-mono text-muted-foreground tabular-nums">
              {isNum(m.previous) ? byUnit(m.previous, m.unit) : "—"}
              {m.previous_label && isNum(m.previous) ? <span className="ml-1 text-xs">({m.previous_label})</span> : null}
            </TableCell>
            {showSector && (
              <TableCell className="text-right font-mono text-muted-foreground tabular-nums">
                {byUnit(m.sector_median, m.unit)}
              </TableCell>
            )}
            <TableCell className="text-xs text-muted-foreground">{m.comment}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function KV({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
      {items.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-2 border-b py-1">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="text-right font-medium">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ScoreGrid({ modules, onPick }: { modules: Record<string, ModuleResult>; onPick?: (k: string) => void }) {
  const order = ["technical", "fundamental", "financial_health", "valuation", "sector", "news", "risk"];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
      {order.map((k) => {
        const m = modules[k];
        return (
          <button
            key={k}
            type="button"
            onClick={() => onPick?.(k)}
            className={cn("rounded-lg border p-3 text-left transition-colors hover:bg-muted", !m?.score && "opacity-70")}
          >
            <div className="text-xs text-muted-foreground">{MODULE_TR[k]}</div>
            <ScoreValue score={m?.score} />
            <div className="text-[11px] text-muted-foreground">
              {k === "risk" ? "100 = düşük risk" : m?.score == null ? "Veri yetersiz" : `Güvenilirlik ${num(m.reliability * 100, 0)}%`}
            </div>
          </button>
        );
      })}
    </div>
  );
}

export { Notes };

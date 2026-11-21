"use client";

import { AlertTriangle, Info } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { LABEL_TR, isNum, scoreClass } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ErrorBox({ error, className }: { error: unknown; className?: string }) {
  const msg = error instanceof Error ? error.message : "Beklenmeyen bir hata oluştu.";
  return (
    <div className={cn("flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm", className)}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
      <span>{msg}</span>
    </div>
  );
}

export function Notes({ notes, className }: { notes?: (string | null | undefined)[]; className?: string }) {
  const list = (notes ?? []).filter(Boolean) as string[];
  if (!list.length) return null;
  return (
    <ul className={cn("space-y-1 text-xs text-muted-foreground", className)}>
      {list.map((n, i) => (
        <li key={i} className="flex gap-1.5">
          <Info className="mt-0.5 size-3 shrink-0" />
          <span>{n}</span>
        </li>
      ))}
    </ul>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-6 w-full" />
      ))}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-6 text-center text-sm text-muted-foreground">{children}</p>;
}

export function ScoreValue({ score, className }: { score: number | null | undefined; className?: string }) {
  return (
    <span className={cn("font-mono text-2xl font-semibold tabular-nums", scoreClass(score), className)}>
      {isNum(score) ? score.toFixed(1) : "—"}
    </span>
  );
}

export function LabelBadge({ label }: { label?: string | null }) {
  if (!label) return <Badge variant="outline">Sınıf yok</Badge>;
  const cls =
    label === "strong"
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
      : label === "weak"
        ? "bg-red-500/15 text-red-700 dark:text-red-300"
        : "bg-amber-500/15 text-amber-700 dark:text-amber-300";
  return <Badge className={cls}>{LABEL_TR[label] ?? label}</Badge>;
}

export function Freshness({ label = "Gün sonu", date }: { label?: string; date?: string | null }) {
  return (
    <Badge variant="outline" className="font-normal text-muted-foreground">
      {label}
      {date ? ` · ${date}` : ""}
    </Badge>
  );
}

export function Section({
  title,
  action,
  children,
  className,
}: {
  title: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="text-base">{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

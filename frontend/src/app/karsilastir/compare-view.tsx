"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { Empty, ErrorBox, Loading, Notes, ScoreValue, Section } from "@/components/common";
import { StockSearch } from "@/components/stock-search";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LABEL_TR, MODULE_TR, MOMENTUM_TR, TREND_TR, multiple, num, pct, price } from "@/lib/format";

type Item = {
  symbol: string; name: string; sector: string | null; price: number | null; price_date: string | null; financial_period: string | null;
  overall: { score: number | null; label: string | null };
  scores: Record<string, number | null>;
  technical: { trend: string | null; rsi_14: number | null; momentum: string | null };
  valuation: Record<string, number | null>;
  ratios: Record<string, number | null>;
  risk: Record<string, number | null>;
};

const ROWS: [string, string, (i: Item) => React.ReactNode][] = [
  ["Fiyat", "Genel", (i) => price(i.price)],
  ["Sektör", "Genel", (i) => i.sector ?? "—"],
  ["Finansal dönem", "Genel", (i) => i.financial_period ?? "—"],
  ["Genel puan", "Genel", (i) => `${num(i.overall.score, 1)} ${i.overall.label ? `(${LABEL_TR[i.overall.label]})` : ""}`],
  ...(["technical", "fundamental", "financial_health", "valuation", "sector", "news", "risk"].map(
    (k) => [MODULE_TR[k], "Puanlar", (i: Item) => <ScoreValue score={i.scores[k]} className="text-base" />] as [string, string, (i: Item) => React.ReactNode],
  )),
  ["Trend", "Teknik", (i) => TREND_TR[i.technical.trend ?? ""] ?? "—"],
  ["Momentum", "Teknik", (i) => MOMENTUM_TR[i.technical.momentum ?? ""] ?? "—"],
  ["RSI 14", "Teknik", (i) => num(i.technical.rsi_14, 1)],
  ["F/K", "Değerleme", (i) => multiple(i.valuation.pe)],
  ["PD/DD", "Değerleme", (i) => multiple(i.valuation.pb)],
  ["FD/FAVÖK", "Değerleme", (i) => multiple(i.valuation.ev_ebitda)],
  ["FD/Satışlar", "Değerleme", (i) => multiple(i.valuation.ev_sales)],
  ["ROE", "Oranlar", (i) => pct(i.ratios.roe)],
  ["Net kâr marjı", "Oranlar", (i) => pct(i.ratios.net_margin)],
  ["FAVÖK marjı", "Oranlar", (i) => pct(i.ratios.ebitda_margin)],
  ["Cari oran", "Oranlar", (i) => num(i.ratios.current_ratio, 2)],
  ["Net borç / FAVÖK", "Oranlar", (i) => multiple(i.ratios.net_debt_to_ebitda)],
  ["Borç / Özkaynak", "Oranlar", (i) => num(i.ratios.liabilities_to_equity, 2)],
  ["Beta", "Risk", (i) => num(i.risk.beta, 2)],
  ["Oynaklık (yıllık)", "Risk", (i) => pct(i.risk.historical_volatility)],
  ["Maksimum düşüş", "Risk", (i) => pct(i.risk.max_drawdown)],
  ["Sharpe", "Risk", (i) => num(i.risk.sharpe, 2)],
];

export function CompareView() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const key = symbols.length >= 2 ? `/compare?symbols=${symbols.join(",")}` : null;
  const { data, error, isLoading } = useSWR<{ items: Item[]; note: string | null }>(key);
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">Hisse karşılaştırma</h1>
      <Section title="Hisseler (2-5)">
        <div className="flex flex-wrap items-center gap-2">
          {symbols.map((s) => (
            <Badge key={s} variant="secondary" className="gap-1 font-mono">
              {s}
              <button type="button" aria-label={`${s} çıkar`} onClick={() => setSymbols((x) => x.filter((y) => y !== s))}>
                <X className="size-3" />
              </button>
            </Badge>
          ))}
          {symbols.length < 5 && (
            <StockSearch
              className="w-64"
              placeholder="Hisse ekle…"
              onSelect={(h) => h.instrument_type === "equity" && setSymbols((x) => (x.includes(h.symbol) ? x : [...x, h.symbol]))}
            />
          )}
          {symbols.length > 0 && <Button variant="ghost" size="sm" onClick={() => setSymbols([])}>Temizle</Button>}
        </div>
      </Section>
      {symbols.length < 2 && <Empty>Karşılaştırmak için en az 2 hisse seçin.</Empty>}
      {error && <ErrorBox error={error} />}
      {isLoading && <Loading rows={10} />}
      {data && (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Gösterge</TableHead>
                {data.items.map((i) => (
                  <TableHead key={i.symbol} className="text-right">
                    <Link href={`/hisse/${i.symbol}`} className="font-mono hover:underline">{i.symbol}</Link>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {ROWS.map(([label, group, fn]) => (
                <TableRow key={label}>
                  <TableCell>
                    <span className="mr-2 text-xs text-muted-foreground">{group}</span>
                    {label}
                  </TableCell>
                  {data.items.map((i) => (
                    <TableCell key={i.symbol} className="text-right font-mono tabular-nums">{fn(i)}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <Notes notes={[data?.note, "Risk puanında 100 düşük risk demektir. Fiyatlar gün sonu verisidir."]} />
    </div>
  );
}

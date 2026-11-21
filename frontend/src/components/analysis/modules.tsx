"use client";

import Link from "next/link";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import useSWR from "swr";

import { Empty, ErrorBox, Loading, Notes } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  DIRECTION_TR,
  HORIZON_TR,
  IMPORTANCE_TR,
  MOMENTUM_TR,
  RSI_TR,
  TREND_TR,
  VOLATILITY_TR,
  VOLUME_TR,
  dateTime,
  isNum,
  money,
  multiple,
  num,
  pct,
  price,
  signedPct,
} from "@/lib/format";

import { KV, MetricTable, ModuleHeader } from "./parts";
import type { ModuleResult } from "./types";

// ---------------------------------------------------------------- teknik

export function TechnicalTab({ m }: { m: ModuleResult }) {
  const a = m.assessments as {
    trend_direction?: string; momentum_strength?: string; rsi_state?: string; volume_support?: string;
    volatility_state?: string; up_down_volume_ratio?: number; atr_pct?: number;
    levels?: { supports: { level: number; touches: number }[]; resistances: { level: number; touches: number }[] };
  };
  return (
    <div className="space-y-5">
      <ModuleHeader m={m} componentNames={{ trend: "Trend (%35)", momentum: "Momentum (%30)", volume: "Hacim (%20)", volatility: "Oynaklık (%15)" }} />
      <KV
        items={[
          ["Trend yönü", TREND_TR[a.trend_direction ?? ""] ?? "—"],
          ["Momentum gücü", MOMENTUM_TR[a.momentum_strength ?? ""] ?? "—"],
          ["Aşırı alım / satım (RSI)", RSI_TR[a.rsi_state ?? ""] ?? "—"],
          ["Hacim desteği", VOLUME_TR[a.volume_support ?? ""] ?? "—"],
          ["Yükseliş / düşüş günü hacim oranı", num(a.up_down_volume_ratio, 2)],
          ["Oynaklık durumu", VOLATILITY_TR[a.volatility_state ?? ""] ?? "—"],
          ["ATR / fiyat", pct(a.atr_pct, 2)],
        ]}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <h4 className="mb-1 text-sm font-medium">Destek seviyeleri</h4>
          {a.levels?.supports?.length ? (
            <ul className="text-sm">
              {a.levels.supports.map((l) => (
                <li key={l.level} className="flex justify-between border-b py-1">
                  <span className="font-mono">{price(l.level)}</span>
                  <span className="text-muted-foreground">{l.touches} dokunuş</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Bulunamadı.</Empty>
          )}
        </div>
        <div>
          <h4 className="mb-1 text-sm font-medium">Direnç seviyeleri</h4>
          {a.levels?.resistances?.length ? (
            <ul className="text-sm">
              {a.levels.resistances.map((l) => (
                <li key={l.level} className="flex justify-between border-b py-1">
                  <span className="font-mono">{price(l.level)}</span>
                  <span className="text-muted-foreground">{l.touches} dokunuş</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Bulunamadı (fiyat tarihi zirveye yakın olabilir).</Empty>
          )}
        </div>
      </div>
      <MetricTable metrics={m.metrics} />
      <Notes notes={m.notes} />
    </div>
  );
}

// ---------------------------------------------------------------- temel

type GrowthRow = { item: string; name: string; ttm_yoy: number | null; annual: number | null; annual_period: string | null; quarter_yoy: number | null; quarter_qoq: number | null };

export function FundamentalTab({ m }: { m: ModuleResult }) {
  const growth = (m.extra.growth as GrowthRow[] | undefined) ?? [];
  const items = (m.extra.statement_items as Record<string, { period: number | null; ttm: number | null; quarter: number | null }>) ?? {};
  const NAMES: Record<string, string> = {
    revenue: "Hasılat", gross_profit: "Brüt kâr", operating_profit: "Faaliyet kârı", ebitda: "FAVÖK",
    net_profit: "Net kâr", parent_net_profit: "Net kâr (ana ortaklık)", operating_cash_flow: "İşletme nakit akışı",
    capex: "Yatırım harcaması", free_cash_flow: "Serbest nakit akışı", total_assets: "Toplam varlıklar",
    equity: "Özkaynaklar", parent_equity: "Ana ortaklık özkaynağı", cash: "Nakit", loans: "Krediler",
    deposits: "Mevduat", net_interest_income: "Net faiz geliri", earned_premiums: "Kazanılmış primler",
  };
  const chart = growth.filter((g) => isNum(g.ttm_yoy)).map((g) => ({ name: g.name, value: (g.ttm_yoy as number) * 100 }));
  return (
    <div className="space-y-5">
      <ModuleHeader m={m} componentNames={{ profitability: "Kârlılık", growth: "Büyüme", cash: "Nakit üretimi", performance: "Finansal performans" }} />
      <div>
        <h4 className="mb-2 text-sm font-medium">Büyüme (nominal TL)</h4>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Kalem</TableHead>
              <TableHead className="text-right">Son 12 ay (yıllık)</TableHead>
              <TableHead className="text-right">Yıllık</TableHead>
              <TableHead className="text-right">Çeyrek (geçen yılın aynı çeyreği)</TableHead>
              <TableHead className="text-right">Çeyrek (önceki çeyrek)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {growth.map((g) => (
              <TableRow key={g.item}>
                <TableCell>{g.name}</TableCell>
                {[g.ttm_yoy, g.annual, g.quarter_yoy, g.quarter_qoq].map((v, i) => (
                  <TableCell key={i} className="text-right font-mono tabular-nums">
                    {isNum(v) ? signedPct(v * 100, 1) : "—"}
                    {i === 1 && g.annual_period && isNum(v) ? <span className="ml-1 text-xs text-muted-foreground">({g.annual_period})</span> : null}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {chart.length > 0 && (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <RTooltip formatter={(v) => `%${Number(v).toFixed(1)}`} />
              <Bar dataKey="value" name="Son 12 ay büyüme" fill="#3b82f6" radius={4} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <div>
        <h4 className="mb-2 text-sm font-medium">Temel kalemler ({m.as_of})</h4>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Kalem</TableHead>
              <TableHead className="text-right">Dönem sonu / kümülatif</TableHead>
              <TableHead className="text-right">Son 12 ay</TableHead>
              <TableHead className="text-right">Son çeyrek</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Object.entries(items).map(([k, v]) => (
              <TableRow key={k}>
                <TableCell>{NAMES[k] ?? k}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{money(v.period)}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{money(v.ttm)}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{money(v.quarter)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <MetricTable metrics={m.metrics} />
      <Notes notes={m.notes} />
    </div>
  );
}

export function HealthTab({ m }: { m: ModuleResult }) {
  return (
    <div className="space-y-5">
      <ModuleHeader m={m} componentNames={{ liquidity: "Likidite", leverage: "Borçluluk", profitability: "Kârlılık", efficiency: "Verimlilik" }} />
      <p className="text-xs text-muted-foreground">Gösterge adının üzerine gelince formülü görünür. &ldquo;Önceki&rdquo; sütunu bir yıl önceki aynı dönemdir.</p>
      <MetricTable metrics={m.metrics} showSector />
      <Notes notes={m.notes} />
    </div>
  );
}

// ---------------------------------------------------------------- değerleme

type Scenario = {
  valid: boolean; reason?: string; value_per_share?: number | null; vs_price?: number | null; terminal_share?: number | null;
  equity_value?: number; enterprise_value?: number; note?: string | null;
  assumptions?: { revenue_growth: number[]; ebitda_margin: number; tax_rate: number; capex_pct_revenue: number; da_pct_revenue: number; wacc_start: number; wacc_end: number; terminal_growth: number };
};

export function ValuationTab({ m }: { m: ModuleResult }) {
  const d = m.extra.dcf as { valid: boolean; reason?: string; note?: string; wacc?: Record<string, number | string>; scenarios?: Record<string, Scenario> };
  const SC: Record<string, string> = { optimistic: "İyimser", base: "Baz", pessimistic: "Kötümser" };
  return (
    <div className="space-y-5">
      <ModuleHeader m={m} componentNames={{ multiples: "Çarpanlar", dcf: "DCF" }} />
      <KV
        items={[
          ["Son fiyat", price(m.extra.price)],
          ["Piyasa değeri", money(m.extra.market_cap)],
          ["Firma değeri", money(m.extra.ev)],
          ["Çarpan karşılaştırma temeli", m.extra.multiples_basis === "sector" ? "Sektör" : m.extra.multiples_basis === "own_history" ? "Şirketin kendi geçmişi" : "Yok"],
        ]}
      />
      <MetricTable metrics={m.metrics} showSector />
      <div className="space-y-2">
        <h4 className="text-sm font-medium">İndirgenmiş nakit akışı (DCF) — 3 senaryo</h4>
        {!d?.valid ? (
          <p className="text-sm text-muted-foreground">DCF hesaplanmadı: {d?.reason}</p>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Varsayım / sonuç</TableHead>
                  {Object.keys(d.scenarios ?? {}).map((k) => (
                    <TableHead key={k} className="text-right">{SC[k] ?? k}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {(
                  [
                    ["Gelir büyümesi (1→5. yıl)", (s: Scenario) => s.assumptions?.revenue_growth.map((g) => `%${Math.round(g * 100)}`).join(" → ")],
                    ["FAVÖK marjı", (s: Scenario) => pct(s.assumptions?.ebitda_margin)],
                    ["Yatırım / hasılat", (s: Scenario) => pct(s.assumptions?.capex_pct_revenue)],
                    ["WACC (1. → 5. yıl)", (s: Scenario) => `${pct(s.assumptions?.wacc_start)} → ${pct(s.assumptions?.wacc_end)}`],
                    ["Uç büyüme oranı", (s: Scenario) => pct(s.assumptions?.terminal_growth)],
                    ["Vergi oranı", (s: Scenario) => pct(s.assumptions?.tax_rate, 0)],
                    ["Firma değeri", (s: Scenario) => money(s.enterprise_value)],
                    ["Özkaynak değeri", (s: Scenario) => money(s.equity_value)],
                    ["Pay başına model değeri", (s: Scenario) => price(s.value_per_share)],
                    ["Son fiyata göre", (s: Scenario) => (isNum(s.vs_price) ? signedPct(s.vs_price * 100, 1) : "—")],
                    ["Uç değerin payı", (s: Scenario) => pct(s.terminal_share, 0)],
                  ] as [string, (s: Scenario) => React.ReactNode][]
                ).map(([label, fn]) => (
                  <TableRow key={label}>
                    <TableCell>{label}</TableCell>
                    {Object.entries(d.scenarios ?? {}).map(([k, s]) => (
                      <TableCell key={k} className="text-right font-mono tabular-nums">{s.valid ? fn(s) : "—"}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <KV
              items={[
                ["Risksiz faiz", pct(d.wacc?.risk_free as number)],
                ["Beta", `${num(d.wacc?.beta as number, 2)} (${d.wacc?.beta_source})`],
                ["Özkaynak maliyeti", pct(d.wacc?.cost_of_equity as number)],
                ["Borç maliyeti (vergi sonrası)", pct(d.wacc?.cost_of_debt_after_tax as number)],
                ["Özkaynak ağırlığı", pct(d.wacc?.equity_weight as number, 0)],
              ]}
            />
            <Notes notes={[d.note, ...Object.values(d.scenarios ?? {}).map((s) => s.note)]} />
          </>
        )}
      </div>
      <Notes notes={m.notes} />
    </div>
  );
}

// ---------------------------------------------------------------- sektör

export function SectorTab({ m, onRefreshPeers, refreshing }: { m: ModuleResult; onRefreshPeers: () => void; refreshing: boolean }) {
  const table = (m.extra.table as Record<string, number | string | null>[] | undefined) ?? [];
  const stats = (m.extra.stats as Record<string, { name: string; median: number | null; average: number | null; company: number | null; position?: string; peer_count: number }>) ?? {};
  const cols: [string, string, (v: unknown) => string][] = [
    ["pe", "F/K", multiple], ["pb", "PD/DD", multiple], ["ev_ebitda", "FD/FAVÖK", multiple], ["roe", "ROE", (v) => pct(v)],
    ["net_margin", "Net marj", (v) => pct(v)], ["liabilities_to_equity", "Borç/Özk.", (v) => num(v, 2)],
    ["revenue_growth", "Gelir büy.", (v) => pct(v)], ["ebitda_margin", "FAVÖK marjı", (v) => pct(v)], ["ocf_margin", "İNA/Hasılat", (v) => pct(v)],
  ];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <ModuleHeader m={m} />
        <Button variant="outline" size="sm" onClick={onRefreshPeers} disabled={refreshing}>
          {refreshing ? "Rakip verileri çekiliyor…" : "Rakiplerin verisini çek"}
        </Button>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Şirket</TableHead>
              {cols.map(([k, label]) => (
                <TableHead key={k} className="text-right">{label}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {table.map((r, i) => (
              <TableRow key={String(r.symbol)} className={i === 0 ? "bg-muted/50 font-medium" : ""}>
                <TableCell>
                  <Link href={`/hisse/${r.symbol}`} className="font-mono hover:underline">{String(r.symbol)}</Link>
                </TableCell>
                {cols.map(([k, , f]) => (
                  <TableCell key={k} className="text-right font-mono tabular-nums">{f(r[k])}</TableCell>
                ))}
              </TableRow>
            ))}
            <TableRow>
              <TableCell className="text-muted-foreground">Sektör medyanı</TableCell>
              {cols.map(([k, , f]) => (
                <TableCell key={k} className="text-right font-mono text-muted-foreground tabular-nums">{f(stats[k]?.median)}</TableCell>
              ))}
            </TableRow>
            <TableRow>
              <TableCell className="text-muted-foreground">Sektör ortalaması</TableCell>
              {cols.map(([k, , f]) => (
                <TableCell key={k} className="text-right font-mono text-muted-foreground tabular-nums">{f(stats[k]?.average)}</TableCell>
              ))}
            </TableRow>
            <TableRow>
              <TableCell className="text-muted-foreground">Şirketin konumu</TableCell>
              {cols.map(([k]) => (
                <TableCell key={k} className="text-right text-xs text-muted-foreground">{stats[k]?.position ?? "—"}</TableCell>
              ))}
            </TableRow>
          </TableBody>
        </Table>
      </div>
      <Notes notes={m.notes} />
    </div>
  );
}

// ---------------------------------------------------------------- haberler

type NewsItem = {
  ref: string; kind: string; source: string; source_reliability: string; published_at: string | null; event_date: string | null;
  title: string; category: string; summary: string; direction: string; importance: string; horizon: string; significance: string;
  positive_effects: string[]; negative_effects: string[]; url: string;
};

export function NewsTab({ m, symbol, onAnalyze, analyzing }: { m: ModuleResult; symbol: string; onAnalyze: () => void; analyzing: boolean }) {
  const items = (m.extra.items as NewsItem[] | undefined) ?? [];
  const { data: raw } = useSWR<{ items: { id: number; title: string; publisher: string; url: string; published_at: string; stocks: { match_type: string }[] }[] }>(`/stocks/${symbol}/news?limit=15`);
  const { data: kap } = useSWR<{ items: { kap_index: number; subject: string | null; summary: string | null; url: string; published_at: string; class: string | null }[] }>(`/stocks/${symbol}/disclosures?limit=15`);
  const REL: Record<string, string> = { official: "Resmî (KAP)", major: "Büyük yayın kuruluşu", other: "Diğer kaynak" };
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <ModuleHeader m={m} />
        <Button variant="outline" size="sm" onClick={onAnalyze} disabled={analyzing}>
          {analyzing ? "AI haberleri değerlendiriyor…" : "Yeni haberleri AI ile değerlendir"}
        </Button>
      </div>
      {items.length > 0 ? (
        <ul className="space-y-3">
          {items.map((n) => (
            <li key={n.ref} className="rounded-lg border p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={n.direction === "positive" ? "default" : n.direction === "negative" ? "destructive" : "secondary"}>
                  {DIRECTION_TR[n.direction]}
                </Badge>
                <Badge variant="outline">{n.category}</Badge>
                <Badge variant="outline">Önem: {IMPORTANCE_TR[n.importance]}</Badge>
                <Badge variant="outline">{HORIZON_TR[n.horizon]}</Badge>
                <span className="ml-auto text-xs text-muted-foreground">
                  {n.source} · {REL[n.source_reliability]} · {dateTime(n.published_at)}
                  {n.event_date ? ` · Olay tarihi: ${n.event_date}` : ""}
                </span>
              </div>
              <a href={n.url} target="_blank" rel="noreferrer" className="mt-2 block font-medium hover:underline">{n.title}</a>
              <p className="mt-1 text-muted-foreground">{n.summary}</p>
              <p className="mt-1">{n.significance}</p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {n.positive_effects.length > 0 && (
                  <ul className="list-inside list-disc text-xs text-emerald-700 dark:text-emerald-400">
                    {n.positive_effects.map((e) => <li key={e}>{e}</li>)}
                  </ul>
                )}
                {n.negative_effects.length > 0 && (
                  <ul className="list-inside list-disc text-xs text-red-700 dark:text-red-400">
                    {n.negative_effects.map((e) => <li key={e}>{e}</li>)}
                  </ul>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>AI ile değerlendirilmiş haber yok.</Empty>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <h4 className="mb-2 text-sm font-medium">KAP bildirimleri</h4>
          {kap?.items?.length ? (
            <ul className="divide-y text-sm">
              {kap.items.map((k) => (
                <li key={k.kap_index} className="py-2">
                  <a href={k.url} target="_blank" rel="noreferrer" className="hover:underline">{k.subject ?? "Bildirim"}</a>
                  <div className="text-xs text-muted-foreground">{dateTime(k.published_at)} {k.summary ? `· ${k.summary}` : ""}</div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Bildirim yok.</Empty>
          )}
        </div>
        <div>
          <h4 className="mb-2 text-sm font-medium">Eşleşen haberler (ham)</h4>
          {raw?.items?.length ? (
            <ul className="divide-y text-sm">
              {raw.items.map((n) => (
                <li key={n.id} className="py-2">
                  <a href={n.url} target="_blank" rel="noreferrer" className="hover:underline">{n.title}</a>
                  <div className="text-xs text-muted-foreground">
                    {n.publisher} · {dateTime(n.published_at)} · eşleşme: {n.stocks[0]?.match_type === "symbol" ? "hisse kodu" : n.stocks[0]?.match_type === "name" ? "şirket adı" : "arama"}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Haber yok.</Empty>
          )}
        </div>
      </div>
      <Notes notes={m.notes} />
    </div>
  );
}

// ---------------------------------------------------------------- risk

export function RiskTab({ m }: { m: ModuleResult }) {
  return (
    <div className="space-y-5">
      <ModuleHeader
        m={m}
        componentNames={{
          historical_volatility: "Oynaklık", beta: "Beta", max_drawdown: "Maks. düşüş", downside_deviation: "Aşağı yönlü sapma",
          leverage: "Borçluluk", liquidity: "Likidite", market_liquidity: "Piyasa likiditesi", profit_stability: "Kâr istikrarı",
        }}
      />
      <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-2 text-sm">
        Risk puanında <strong>100 düşük risk, 0 yüksek risk</strong> demektir. Alt puanlarda da yüksek değer daha az risktir.
      </p>
      <MetricTable metrics={m.metrics} />
      <Notes notes={m.notes} />
    </div>
  );
}

// ---------------------------------------------------------------- finansal tablolar

type Statements = {
  periods: { key: string; inflation_adjusted: boolean | null; inflation_basis: string | null }[];
  items: { code: string; name: string; values: Record<string, number | null> }[];
  message?: string; note?: string; fetched_at?: string;
};

export function StatementsTab({ symbol }: { symbol: string }) {
  const [kind, setKind] = useState<"income" | "balance" | "cashflow">("income");
  const { data, error, isLoading } = useSWR<Statements>(`/stocks/${symbol}/financials?statement=${kind}&periods=8`);
  const KINDS = { income: "Gelir tablosu", balance: "Bilanço", cashflow: "Nakit akış" } as const;
  return (
    <div className="space-y-3">
      <div className="flex gap-1">
        {(Object.keys(KINDS) as (keyof typeof KINDS)[]).map((k) => (
          <Button key={k} size="sm" variant={kind === k ? "secondary" : "ghost"} onClick={() => setKind(k)}>{KINDS[k]}</Button>
        ))}
      </div>
      {error && <ErrorBox error={error} />}
      {isLoading && <Loading rows={8} />}
      {data?.message && <Empty>{data.message}</Empty>}
      {data && data.items.length > 0 && (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-56">Kalem</TableHead>
                {data.periods.map((p) => (
                  <TableHead key={p.key} className="text-right" title={p.inflation_basis ?? undefined}>
                    {p.key}
                    {p.inflation_adjusted === true ? " *" : p.inflation_adjusted == null ? " ?" : ""}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((it) => (
                <TableRow key={it.code}>
                  <TableCell className="text-xs">{it.name}</TableCell>
                  {data.periods.map((p) => (
                    <TableCell key={p.key} className="text-right font-mono text-xs tabular-nums">{money(it.values[p.key])}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <Notes notes={[data?.note, "* TMS 29 enflasyon muhasebesi uygulanmış dönem. ? Uygulama durumu teyit edilmedi (finans kuruluşları)."]} />
    </div>
  );
}

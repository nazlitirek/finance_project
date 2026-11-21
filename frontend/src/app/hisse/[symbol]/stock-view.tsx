"use client";

import { FileText, RefreshCw, Star } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import {
  FundamentalTab,
  HealthTab,
  NewsTab,
  RiskTab,
  SectorTab,
  StatementsTab,
  TechnicalTab,
  ValuationTab,
} from "@/components/analysis/modules";
import { ScoreGrid } from "@/components/analysis/parts";
import type { Analysis } from "@/components/analysis/types";
import { ErrorBox, Freshness, LabelBadge, Loading, Notes, ScoreValue, Section } from "@/components/common";
import { PriceChart } from "@/components/price-chart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiDelete, apiPost } from "@/lib/api";
import { LABEL_TR, changeClass, date, dateTime, money, num, pct, price, signedPct } from "@/lib/format";

type Stock = { symbol: string; name: string; instrument_type: string; sector: string | null };
type Quote = {
  price: number | null; as_of?: string; previous_close?: number | null; change?: number | null; change_pct?: number | null;
  turnover?: number | null; fetched_at?: string; note?: string; message?: string;
};
type Reports = { items: { id: number; created_at: string; status: string; model: string | null; overall_score: number | null; overall_label: string | null; error: string | null }[] };

export function StockView() {
  const { symbol: raw } = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(raw).toUpperCase();
  const router = useRouter();
  const [tab, setTab] = useState("technical");
  const [busy, setBusy] = useState<string | null>(null);

  const info = useSWR<Stock>(`/stocks/${symbol}`);
  const quote = useSWR<Quote>(`/stocks/${symbol}/quote`);
  const isEquity = info.data?.instrument_type === "equity";
  const analysis = useSWR<Analysis>(isEquity ? `/stocks/${symbol}/analysis` : null);
  const watch = useSWR<{ items: { symbol: string }[] }>("/watchlist");
  const reports = useSWR<Reports>(isEquity ? `/stocks/${symbol}/reports` : null);
  const isFav = !!watch.data?.items.some((w) => w.symbol === symbol);

  async function run(key: string, fn: () => Promise<unknown>, ok: string) {
    setBusy(key);
    try {
      await fn();
      toast.success(ok);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "İşlem başarısız.");
    } finally {
      setBusy(null);
    }
  }

  const refreshAll = () => Promise.all([quote.mutate(), analysis.mutate(), reports.mutate()]);

  if (info.error) return <ErrorBox error={info.error} />;
  if (!info.data) return <Loading rows={6} />;
  const q = quote.data;
  const a = analysis.data;

  return (
    <div className="space-y-6">
      {/* üst bölüm */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-bold">{info.data.symbol}</h1>
            {info.data.sector && <Badge variant="outline">{info.data.sector}</Badge>}
            {!isEquity && <Badge variant="secondary">Endeks</Badge>}
          </div>
          <p className="text-muted-foreground">{info.data.name}</p>
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="text-3xl font-semibold tabular-nums">{isEquity ? price(q?.price) : num(q?.price)}</span>
            <span className={`text-lg tabular-nums ${changeClass(q?.change_pct)}`}>{signedPct(q?.change_pct)}</span>
            <span className="text-sm text-muted-foreground">Hacim: {money(q?.turnover)}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Freshness date={q?.as_of ? date(q.as_of) : null} />
            <span>Son veri güncellemesi: {dateTime(q?.fetched_at)}</span>
          </div>
        </div>
        {isEquity && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant={isFav ? "secondary" : "outline"}
              disabled={busy === "fav"}
              onClick={() =>
                run(
                  "fav",
                  async () => {
                    if (isFav) await apiDelete(`/watchlist/${symbol}`);
                    else await apiPost("/watchlist", { symbol });
                    await watch.mutate();
                  },
                  isFav ? "Favorilerden çıkarıldı." : "Favorilere eklendi.",
                )
              }
            >
              <Star className={isFav ? "fill-current" : ""} />
              {isFav ? "Favoride" : "Favorilere ekle"}
            </Button>
            <Button
              variant="outline"
              disabled={busy === "refresh"}
              onClick={() =>
                run("refresh", async () => {
                  await apiPost(`/stocks/${symbol}/refresh`);
                  await refreshAll();
                }, "Fiyat, finansal tablo ve haberler güncellendi.")
              }
            >
              <RefreshCw className={busy === "refresh" ? "animate-spin" : ""} />
              {busy === "refresh" ? "Güncelleniyor…" : "Verileri güncelle"}
            </Button>
            <Button
              disabled={busy === "report"}
              onClick={() =>
                run("report", async () => {
                  const r = await apiPost<{ id: number; status: string; error: string | null }>(`/stocks/${symbol}/report`);
                  await reports.mutate();
                  if (r.status !== "completed") throw new Error(r.error ?? "Rapor oluşturulamadı.");
                  router.push(`/rapor/${r.id}`);
                }, "AI raporu hazır.")
              }
            >
              <FileText />
              {busy === "report" ? "AI raporu hazırlanıyor (1-4 dk)…" : "AI raporu oluştur"}
            </Button>
          </div>
        )}
      </div>

      <Section title="Fiyat grafiği">
        <PriceChart symbol={symbol} />
      </Section>

      {isEquity && (
        <>
          {analysis.error && <ErrorBox error={analysis.error} />}
          {!a && !analysis.error && <Loading rows={4} />}
          {a && (
            <>
              <Card>
                <CardContent className="space-y-4">
                  <div className="flex flex-wrap items-center gap-4">
                    <div>
                      <div className="text-sm text-muted-foreground">Genel değerlendirme</div>
                      <div className="flex items-center gap-2">
                        <ScoreValue score={a.overall.score} className="text-4xl" />
                        <LabelBadge label={a.overall.label} />
                      </div>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      <div>Veri kapsamı: {pct(a.overall.coverage, 0)}</div>
                      <div>Finansal dönem: {a.financial_period ?? "—"}</div>
                      {a.overall.missing_modules.length > 0 && <div>Puanlanamayan: {a.overall.missing_modules.join(", ")}</div>}
                    </div>
                  </div>
                  <ScoreGrid modules={a.modules} onPick={setTab} />
                  <Notes notes={[a.overall.note, a.overall.disclaimer]} />
                </CardContent>
              </Card>

              <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
                <TabsList className="flex h-auto flex-wrap">
                  <TabsTrigger value="technical">Teknik</TabsTrigger>
                  <TabsTrigger value="fundamental">Temel</TabsTrigger>
                  <TabsTrigger value="financial_health">Finansal sağlık</TabsTrigger>
                  <TabsTrigger value="valuation">Değerleme</TabsTrigger>
                  <TabsTrigger value="sector">Sektör</TabsTrigger>
                  <TabsTrigger value="news">Haberler ve KAP</TabsTrigger>
                  <TabsTrigger value="risk">Risk</TabsTrigger>
                  <TabsTrigger value="statements">Finansal tablolar</TabsTrigger>
                  <TabsTrigger value="reports">AI raporları</TabsTrigger>
                </TabsList>
                <Card className="mt-3">
                  <CardContent>
                    <TabsContent value="technical"><TechnicalTab m={a.modules.technical} /></TabsContent>
                    <TabsContent value="fundamental"><FundamentalTab m={a.modules.fundamental} /></TabsContent>
                    <TabsContent value="financial_health"><HealthTab m={a.modules.financial_health} /></TabsContent>
                    <TabsContent value="valuation"><ValuationTab m={a.modules.valuation} /></TabsContent>
                    <TabsContent value="sector">
                      <SectorTab
                        m={a.modules.sector}
                        refreshing={busy === "peers"}
                        onRefreshPeers={() =>
                          run("peers", async () => {
                            await apiPost(`/stocks/${symbol}/peers/refresh`);
                            await analysis.mutate();
                          }, "Rakiplerin verisi güncellendi.")
                        }
                      />
                    </TabsContent>
                    <TabsContent value="news">
                      <NewsTab
                        m={a.modules.news}
                        symbol={symbol}
                        analyzing={busy === "news"}
                        onAnalyze={() =>
                          run("news", async () => {
                            const r = await apiPost<{ analyzed: number }>(`/stocks/${symbol}/news/analyze`);
                            await analysis.mutate();
                            toast.message(`${r.analyzed} haber/bildirim değerlendirildi.`);
                          }, "Haber analizi tamamlandı.")
                        }
                      />
                    </TabsContent>
                    <TabsContent value="risk"><RiskTab m={a.modules.risk} /></TabsContent>
                    <TabsContent value="statements"><StatementsTab symbol={symbol} /></TabsContent>
                    <TabsContent value="reports">
                      {reports.data?.items.length ? (
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Tarih</TableHead>
                              <TableHead>Durum</TableHead>
                              <TableHead className="text-right">Genel puan</TableHead>
                              <TableHead>Model</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {reports.data.items.map((r) => (
                              <TableRow key={r.id}>
                                <TableCell>
                                  <Link href={`/rapor/${r.id}`} className="hover:underline">{dateTime(r.created_at)}</Link>
                                </TableCell>
                                <TableCell>{r.status === "completed" ? "Tamamlandı" : r.status === "failed" ? `Hata: ${r.error}` : "Bekliyor"}</TableCell>
                                <TableCell className="text-right font-mono">
                                  {num(r.overall_score, 1)} {r.overall_label ? `(${LABEL_TR[r.overall_label]})` : ""}
                                </TableCell>
                                <TableCell className="text-xs text-muted-foreground">{r.model ?? "—"}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      ) : (
                        <p className="py-6 text-center text-sm text-muted-foreground">Henüz rapor yok. Sağ üstten &ldquo;AI raporu oluştur&rdquo; ile başlayın.</p>
                      )}
                    </TabsContent>
                  </CardContent>
                </Card>
              </Tabs>
            </>
          )}
        </>
      )}
      <Notes notes={[q?.note]} />
    </div>
  );
}

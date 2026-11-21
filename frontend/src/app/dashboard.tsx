"use client";

import Link from "next/link";
import useSWR from "swr";

import { Empty, ErrorBox, Freshness, Loading, Notes, Section } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { changeClass, date, dateTime, money, num, signedPct } from "@/lib/format";

type Mover = { symbol: string; name: string; close: number; change_pct: number; turnover: number };
type Dash = {
  indices: { symbol: string; name: string; value: number | null; as_of?: string; change_pct?: number | null; message?: string }[];
  movers: { as_of: string | null; gainers: Mover[]; losers: Mover[]; turnover: Mover[]; note?: string | null; coverage: number };
  disclosures: { kap_index: number; symbol: string | null; company: string; published_at: string; subject: string | null; url: string }[];
  news: { id: number; title: string; publisher: string | null; url: string; published_at: string | null; stocks: { symbol: string }[] }[];
  favorites: { symbol: string; name: string }[];
  sources: { code: string; name: string; enabled: boolean; last_success_at: string | null; last_error_at: string | null }[];
  note: string;
};

function MoverTable({ rows, valueKey }: { rows: Mover[]; valueKey: "change_pct" | "turnover" }) {
  if (!rows.length) return <Empty>Veri yok.</Empty>;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Hisse</TableHead>
          <TableHead className="text-right">Kapanış</TableHead>
          <TableHead className="text-right">{valueKey === "turnover" ? "Hacim" : "Değişim"}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((m) => (
          <TableRow key={m.symbol}>
            <TableCell>
              <Link href={`/hisse/${m.symbol}`} className="font-mono font-medium hover:underline">
                {m.symbol}
              </Link>
            </TableCell>
            <TableCell className="text-right tabular-nums">{num(m.close)}</TableCell>
            <TableCell className={`text-right tabular-nums ${valueKey === "change_pct" ? changeClass(m.change_pct) : ""}`}>
              {valueKey === "turnover" ? money(m.turnover) : signedPct(m.change_pct)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function Dashboard() {
  const { data, error, isLoading } = useSWR<Dash>("/dashboard");
  if (error) return <ErrorBox error={error} />;
  if (isLoading || !data) return <Loading rows={8} />;
  const mv = data.movers;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Piyasa özeti</h1>
        <Freshness date={mv.as_of ? date(mv.as_of) : null} />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {data.indices.map((i) => (
          <Card key={i.symbol}>
            <CardContent className="space-y-1">
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>{i.name}</span>
                {i.value != null && (
                  <Link href={`/hisse/${i.symbol}`} className="font-mono text-xs hover:underline">
                    {i.symbol}
                  </Link>
                )}
              </div>
              {i.value != null ? (
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-semibold tabular-nums">{num(i.value)}</span>
                  <span className={`text-sm tabular-nums ${changeClass(i.change_pct)}`}>{signedPct(i.change_pct)}</span>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">{i.message}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
      <Notes notes={[data.note, mv.note]} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Section title="En çok yükselenler">
          <MoverTable rows={mv.gainers} valueKey="change_pct" />
        </Section>
        <Section title="En çok düşenler">
          <MoverTable rows={mv.losers} valueKey="change_pct" />
        </Section>
        <Section title="En yüksek hacim">
          <MoverTable rows={mv.turnover} valueKey="turnover" />
        </Section>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Son KAP bildirimleri">
          {data.disclosures.length ? (
            <ul className="divide-y text-sm">
              {data.disclosures.map((d) => (
                <li key={d.kap_index} className="flex gap-2 py-2">
                  {d.symbol ? (
                    <Link href={`/hisse/${d.symbol}`} className="w-16 shrink-0 font-mono font-medium hover:underline">
                      {d.symbol}
                    </Link>
                  ) : (
                    <span className="w-16 shrink-0 text-muted-foreground">—</span>
                  )}
                  <a href={d.url} target="_blank" rel="noreferrer" className="flex-1 hover:underline">
                    {d.subject || d.company}
                  </a>
                  <span className="shrink-0 text-xs text-muted-foreground">{dateTime(d.published_at)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Bildirim yok.</Empty>
          )}
        </Section>
        <Section title="Son finans haberleri">
          {data.news.length ? (
            <ul className="divide-y text-sm">
              {data.news.map((n) => (
                <li key={n.id} className="space-y-1 py-2">
                  <a href={n.url} target="_blank" rel="noreferrer" className="hover:underline">
                    {n.title}
                  </a>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>{n.publisher}</span>
                    <span>{dateTime(n.published_at)}</span>
                    {n.stocks.map((s) => (
                      <Link key={s.symbol} href={`/hisse/${s.symbol}`}>
                        <Badge variant="outline" className="font-mono">
                          {s.symbol}
                        </Badge>
                      </Link>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Haber yok.</Empty>
          )}
        </Section>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Favoriler" action={<Link href="/favoriler" className="text-sm text-muted-foreground hover:underline">Tümü</Link>}>
          {data.favorites.length ? (
            <div className="flex flex-wrap gap-2">
              {data.favorites.map((f) => (
                <Link key={f.symbol} href={`/hisse/${f.symbol}`}>
                  <Badge variant="secondary" className="font-mono">
                    {f.symbol}
                  </Badge>
                </Link>
              ))}
            </div>
          ) : (
            <Empty>Henüz favori yok. Hisse sayfasından ekleyebilirsiniz.</Empty>
          )}
        </Section>
        <Section title="Veri kaynakları">
          <ul className="space-y-1 text-sm">
            {data.sources.map((s) => (
              <li key={s.code} className="flex items-center justify-between gap-2">
                <span className={s.enabled ? "" : "text-muted-foreground line-through"}>{s.name}</span>
                <span className="text-xs text-muted-foreground">
                  {!s.enabled
                    ? "Kapalı"
                    : s.last_error_at && (!s.last_success_at || s.last_error_at > s.last_success_at)
                      ? `Son hata: ${dateTime(s.last_error_at)}`
                      : `Son güncelleme: ${dateTime(s.last_success_at)}`}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">Fiyatlar gün sonu verisidir; gerçek zamanlı değildir.</p>
        </Section>
      </div>
    </div>
  );
}

"use client";

import { Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Empty, ErrorBox, Loading, Notes, Section } from "@/components/common";
import { StockSearch } from "@/components/stock-search";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiDelete, apiPost } from "@/lib/api";
import { changeClass, date, dateTime, money, num, price, signedPct } from "@/lib/format";

type Pos = {
  symbol: string; quantity: number; avg_cost: number | null; cost_basis: number; price: number | null; price_date: string | null;
  market_value: number | null; unrealized_pnl: number | null; unrealized_pct: number | null; realized_pnl: number; closed: boolean;
};
type Portfolio = {
  name: string; positions: Pos[]; total_cost: number; market_value: number; unrealized_pnl: number; unrealized_pct: number | null;
  realized_pnl: number; missing_prices: string[]; note: string;
};
type Txs = { items: { id: number; symbol: string; side: "buy" | "sell"; quantity: number; price: number; fee: number; traded_at: string; note: string | null }[] };

const today = () => new Date().toISOString().slice(0, 10);

export function PortfolioView() {
  const pf = useSWR<Portfolio>("/portfolio");
  const txs = useSWR<Txs>("/portfolio/transactions");
  const [form, setForm] = useState({ symbol: "", side: "buy", quantity: "", price: "", fee: "0", date: today(), note: "" });
  const [saving, setSaving] = useState(false);

  async function refresh() {
    await Promise.all([pf.mutate(), txs.mutate()]);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.symbol) return toast.error("Hisse seçin.");
    setSaving(true);
    try {
      await apiPost("/portfolio/transactions", {
        symbol: form.symbol, side: form.side, quantity: Number(form.quantity.replace(",", ".")),
        price: Number(form.price.replace(",", ".")), fee: Number(form.fee.replace(",", ".") || 0),
        traded_at: new Date(`${form.date}T12:00:00`).toISOString(), note: form.note || null,
      });
      toast.success("İşlem eklendi.");
      setForm((f) => ({ ...f, quantity: "", price: "", fee: "0", note: "" }));
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "İşlem eklenemedi.");
    } finally {
      setSaving(false);
    }
  }

  const p = pf.data;
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">Kişisel portföy</h1>
      {pf.error && <ErrorBox error={pf.error} />}
      {p && (
        <div className="grid gap-3 sm:grid-cols-4">
          {[
            ["Toplam maliyet", money(p.total_cost)],
            ["Güncel değer", money(p.market_value)],
            ["Gerçekleşmemiş kâr/zarar", <span key="u" className={changeClass(p.unrealized_pnl)}>{money(p.unrealized_pnl)} ({signedPct(p.unrealized_pct)})</span>],
            ["Gerçekleşen kâr/zarar", <span key="r" className={changeClass(p.realized_pnl)}>{money(p.realized_pnl)}</span>],
          ].map(([k, v]) => (
            <Card key={String(k)}>
              <CardContent>
                <div className="text-sm text-muted-foreground">{k}</div>
                <div className="text-lg font-semibold tabular-nums">{v}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <Section title="İşlem ekle">
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1">
            <Label>Hisse</Label>
            {form.symbol ? (
              <div className="flex items-center gap-2">
                <span className="font-mono font-semibold">{form.symbol}</span>
                <Button type="button" size="xs" variant="ghost" onClick={() => setForm({ ...form, symbol: "" })}>Değiştir</Button>
              </div>
            ) : (
              <StockSearch placeholder="Hisse seç…" onSelect={(h) => h.instrument_type === "equity" && setForm({ ...form, symbol: h.symbol })} />
            )}
          </div>
          <div className="space-y-1">
            <Label htmlFor="side">İşlem</Label>
            <select id="side" value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })}
              className="h-8 w-full rounded-lg border bg-background px-2 text-sm">
              <option value="buy">Alış</option>
              <option value="sell">Satış</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="qty">Lot</Label>
            <Input id="qty" inputMode="decimal" required value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="price">Fiyat (TL)</Label>
            <Input id="price" inputMode="decimal" required value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="fee">Komisyon (TL)</Label>
            <Input id="fee" inputMode="decimal" value={form.fee} onChange={(e) => setForm({ ...form, fee: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="date">Tarih</Label>
            <Input id="date" type="date" max={today()} required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </div>
          <div className="space-y-1 lg:col-span-2">
            <Label htmlFor="note">Not</Label>
            <Input id="note" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </div>
          <div className="lg:col-span-4">
            <Button type="submit" disabled={saving}>{saving ? "Kaydediliyor…" : "İşlemi ekle"}</Button>
          </div>
        </form>
      </Section>
      <Section title="Pozisyonlar">
        {pf.isLoading && <Loading />}
        {p && (p.positions.length === 0 ? <Empty>Henüz işlem yok.</Empty> : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Hisse</TableHead>
                  <TableHead className="text-right">Lot</TableHead>
                  <TableHead className="text-right">Ort. maliyet</TableHead>
                  <TableHead className="text-right">Son kapanış</TableHead>
                  <TableHead className="text-right">Güncel değer</TableHead>
                  <TableHead className="text-right">Gerçekleşmemiş K/Z</TableHead>
                  <TableHead className="text-right">Gerçekleşen K/Z</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {p.positions.map((x) => (
                  <TableRow key={x.symbol} className={x.closed ? "text-muted-foreground" : ""}>
                    <TableCell><Link href={`/hisse/${x.symbol}`} className="font-mono font-medium hover:underline">{x.symbol}</Link>{x.closed && " (kapalı)"}</TableCell>
                    <TableCell className="text-right tabular-nums">{num(x.quantity, 4)}</TableCell>
                    <TableCell className="text-right tabular-nums">{price(x.avg_cost)}</TableCell>
                    <TableCell className="text-right tabular-nums">{price(x.price)}<div className="text-[11px] text-muted-foreground">{date(x.price_date)}</div></TableCell>
                    <TableCell className="text-right tabular-nums">{money(x.market_value)}</TableCell>
                    <TableCell className={`text-right tabular-nums ${changeClass(x.unrealized_pnl)}`}>{money(x.unrealized_pnl)} <span className="text-xs">{signedPct(x.unrealized_pct)}</span></TableCell>
                    <TableCell className={`text-right tabular-nums ${changeClass(x.realized_pnl)}`}>{money(x.realized_pnl)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ))}
        <Notes className="mt-3" notes={[p?.note, p?.missing_prices.length ? `Fiyatı olmayan: ${p.missing_prices.join(", ")}` : null]} />
      </Section>
      <Section title="İşlem geçmişi">
        {txs.data && (txs.data.items.length === 0 ? <Empty>İşlem yok.</Empty> : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tarih</TableHead>
                <TableHead>Hisse</TableHead>
                <TableHead>İşlem</TableHead>
                <TableHead className="text-right">Lot</TableHead>
                <TableHead className="text-right">Fiyat</TableHead>
                <TableHead className="text-right">Komisyon</TableHead>
                <TableHead>Not</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {txs.data.items.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="text-xs">{dateTime(t.traded_at)}</TableCell>
                  <TableCell className="font-mono">{t.symbol}</TableCell>
                  <TableCell>{t.side === "buy" ? "Alış" : "Satış"}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(t.quantity, 4)}</TableCell>
                  <TableCell className="text-right tabular-nums">{price(t.price)}</TableCell>
                  <TableCell className="text-right tabular-nums">{price(t.fee)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{t.note}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon-sm" aria-label="İşlemi sil" onClick={async () => {
                      try {
                        await apiDelete(`/portfolio/transactions/${t.id}`);
                        toast.success("İşlem silindi.");
                        await refresh();
                      } catch (err) {
                        toast.error(err instanceof Error ? err.message : "Silinemedi.");
                      }
                    }}>
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ))}
      </Section>
    </div>
  );
}

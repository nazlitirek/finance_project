"use client";

import { Bell, RotateCcw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Empty, ErrorBox, Loading, Notes, Section } from "@/components/common";
import { StockSearch } from "@/components/stock-search";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiDelete, apiPost } from "@/lib/api";
import { dateTime, price } from "@/lib/format";

type Alerts = {
  items: {
    id: number; symbol: string; name: string; condition: "above" | "below"; target_price: number; is_active: boolean;
    created_at: string; triggered_at: string | null; triggered_price: number | null; note: string | null;
    current?: { price: number | null; as_of: string | null };
  }[];
  note: string;
};

export default function AlertsPage() {
  const { data, error, isLoading, mutate } = useSWR<Alerts>("/alerts");
  const [form, setForm] = useState({ symbol: "", condition: "above", target: "", note: "" });
  // İzin değişince yeniden okumak için sayaç (Notification.permission için olay yok)
  const [, setPermVersion] = useState(0);
  const perm = useSyncExternalStore(
    () => () => {},
    () => (typeof Notification === "undefined" ? "unsupported" : Notification.permission),
    () => "default",
  );

  async function act(fn: () => Promise<unknown>, ok?: string) {
    try {
      await fn();
      await mutate();
      if (ok) toast.success(ok);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "İşlem başarısız.");
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.symbol) return toast.error("Hisse seçin.");
    await act(async () => {
      const r = await apiPost<{ already_met: boolean; message: string | null }>("/alerts", {
        symbol: form.symbol, condition: form.condition, target_price: Number(form.target.replace(",", ".")), note: form.note || null,
      });
      if (r.already_met && r.message) toast.warning(r.message);
      setForm({ symbol: "", condition: "above", target: "", note: "" });
    }, "Alarm oluşturuldu.");
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Fiyat alarmları</h1>
        {perm !== "granted" && perm !== "unsupported" && (
          <Button variant="outline" size="sm" onClick={async () => {
            if (typeof Notification === "undefined") return toast.error("Tarayıcı bildirimleri desteklenmiyor.");
            const r = await Notification.requestPermission();
            setPermVersion((v) => v + 1);
            if (r === "granted") toast.success("Tarayıcı bildirimleri açık.");
            else toast.warning("Bildirim izni verilmedi; alarmlar sadece uygulama içinde gösterilecek.");
          }}>
            <Bell /> Tarayıcı bildirimlerine izin ver
          </Button>
        )}
      </div>
      <Section title="Yeni alarm">
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div className="space-y-1 lg:col-span-2">
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
            <Label htmlFor="cond">Koşul</Label>
            <select id="cond" value={form.condition} onChange={(e) => setForm({ ...form, condition: e.target.value })}
              className="h-8 w-full rounded-lg border bg-background px-2 text-sm">
              <option value="above">Fiyat üzerine çıkarsa</option>
              <option value="below">Fiyat altına düşerse</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="target">Hedef fiyat (TL)</Label>
            <Input id="target" inputMode="decimal" required value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} />
          </div>
          <div className="flex items-end">
            <Button type="submit">Alarm ekle</Button>
          </div>
        </form>
      </Section>
      {error && <ErrorBox error={error} />}
      {isLoading && <Loading />}
      <Section title="Alarmlar" action={<Button size="sm" variant="outline" onClick={() => act(async () => {
        const r = await apiPost<{ triggered: number }>("/alerts/check");
        toast.message(`${r.triggered} alarm tetiklendi.`);
      })}>Şimdi kontrol et</Button>}>
        {data && (data.items.length === 0 ? <Empty>Alarm yok.</Empty> : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Hisse</TableHead>
                <TableHead>Koşul</TableHead>
                <TableHead className="text-right">Son kapanış</TableHead>
                <TableHead>Durum</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((a) => (
                <TableRow key={a.id}>
                  <TableCell><Link href={`/hisse/${a.symbol}`} className="font-mono font-medium hover:underline">{a.symbol}</Link></TableCell>
                  <TableCell>{a.condition === "above" ? "≥" : "≤"} {price(a.target_price)}</TableCell>
                  <TableCell className="text-right tabular-nums">{price(a.current?.price)}</TableCell>
                  <TableCell>
                    {a.is_active ? <Badge variant="secondary">Aktif</Badge> : (
                      <span className="text-sm">
                        <Badge>Tetiklendi</Badge>{" "}
                        <span className="text-xs text-muted-foreground">{dateTime(a.triggered_at)} · {price(a.triggered_price)}</span>
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {!a.is_active && (
                      <Button variant="ghost" size="icon-sm" aria-label="Yeniden etkinleştir" onClick={() => act(() => apiPost(`/alerts/${a.id}/reactivate`), "Alarm yeniden etkin.")}>
                        <RotateCcw />
                      </Button>
                    )}
                    <Button variant="ghost" size="icon-sm" aria-label="Alarmı sil" onClick={() => act(() => apiDelete(`/alerts/${a.id}`), "Alarm silindi.")}>
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ))}
      </Section>
      <Notes notes={[data?.note, "Bu sayfa (veya uygulamanın herhangi bir sayfası) açıkken tetiklenen alarmlar dakikada bir kontrol edilir ve bildirim gösterilir."]} />
    </div>
  );
}

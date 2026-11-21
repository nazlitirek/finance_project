"use client";

import { Trash2 } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import useSWR from "swr";

import { Empty, ErrorBox, Loading, Notes, Section } from "@/components/common";
import { StockSearch } from "@/components/stock-search";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiDelete, apiPost } from "@/lib/api";
import { changeClass, date, price, signedPct } from "@/lib/format";

type Watch = { items: { symbol: string; name: string; price: number | null; as_of: string | null; change_pct: number | null }[]; note: string };

export default function FavoritesPage() {
  const { data, error, isLoading, mutate } = useSWR<Watch>("/watchlist");

  async function act(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn();
      await mutate();
      toast.success(ok);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "İşlem başarısız.");
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">Favoriler</h1>
      <Section title="Favori ekle">
        <StockSearch
          className="max-w-sm"
          placeholder="Eklenecek hisse…"
          onSelect={(h) => act(() => apiPost("/watchlist", { symbol: h.symbol }), `${h.symbol} favorilere eklendi.`)}
        />
      </Section>
      {error && <ErrorBox error={error} />}
      {isLoading && <Loading />}
      {data && (data.items.length === 0 ? (
        <Empty>Henüz favori hisse yok.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Hisse</TableHead>
              <TableHead>Şirket</TableHead>
              <TableHead className="text-right">Son kapanış</TableHead>
              <TableHead className="text-right">Günlük değişim</TableHead>
              <TableHead>Tarih</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((w) => (
              <TableRow key={w.symbol}>
                <TableCell><Link href={`/hisse/${w.symbol}`} className="font-mono font-medium hover:underline">{w.symbol}</Link></TableCell>
                <TableCell className="max-w-xs truncate">{w.name}</TableCell>
                <TableCell className="text-right tabular-nums">{price(w.price)}</TableCell>
                <TableCell className={`text-right tabular-nums ${changeClass(w.change_pct)}`}>{signedPct(w.change_pct)}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{date(w.as_of)}</TableCell>
                <TableCell className="text-right">
                  <Button variant="ghost" size="icon-sm" aria-label={`${w.symbol} favorilerden çıkar`}
                    onClick={() => act(() => apiDelete(`/watchlist/${w.symbol}`), `${w.symbol} çıkarıldı.`)}>
                    <Trash2 />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ))}
      <Notes notes={[data?.note, "Favori hisselerin finansal tabloları her gece, haberleri 15 dakikada bir güncellenir (backend açıkken)."]} />
    </div>
  );
}

"use client";

import {
  AreaSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
} from "lightweight-charts";
import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { ErrorBox, Notes } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Point = { date: string; value: number };
type ChartData = {
  bars: { date: string; close: number | null; high: number | null; low: number | null; turnover: number | null }[];
  overlays: Record<string, Point[]>;
  note?: string;
  message?: string;
};

const RANGES = [
  { key: "1d", label: "1G" },
  { key: "1w", label: "1H" },
  { key: "1m", label: "1A" },
  { key: "3m", label: "3A" },
  { key: "6m", label: "6A" },
  { key: "1y", label: "1Y" },
  { key: "3y", label: "3Y" },
];
const OVERLAYS = [
  { key: "sma_20", label: "SMA 20", color: "#f59e0b" },
  { key: "sma_50", label: "SMA 50", color: "#3b82f6" },
  { key: "sma_200", label: "SMA 200", color: "#a855f7" },
  { key: "ema_21", label: "EMA 21", color: "#14b8a6" },
  { key: "bb", label: "Bollinger", color: "#94a3b8" },
];

/** Kapanış çizgisi + gün içi en yüksek/en düşük aralığı + TL hacim. Kaynakta açılış fiyatı olmadığı için mum grafik yok. */
export function PriceChart({ symbol }: { symbol: string }) {
  const [range, setRange] = useState("1y");
  const [active, setActive] = useState<string[]>(["sma_50"]);
  const { resolvedTheme } = useTheme();
  const box = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const key = `/stocks/${symbol}/chart?range=${range}&overlays=${active.join(",")}`;
  const { data, error, isLoading } = useSWR<ChartData>(key, { keepPreviousData: true });

  useEffect(() => {
    if (!box.current || !data?.bars?.length) return;
    const dark = resolvedTheme === "dark";
    const text = dark ? "#a1a1aa" : "#52525b";
    const grid = dark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)";
    const chart = createChart(box.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: text },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      localization: { locale: "tr-TR" },
    });
    chartRef.current = chart;

    const bars = data.bars.filter((b) => b.close != null);
    const range = chart.addSeries(AreaSeries, {
      lineVisible: false,
      topColor: dark ? "rgba(59,130,246,0.12)" : "rgba(59,130,246,0.10)",
      bottomColor: "rgba(59,130,246,0)",
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    range.setData(bars.filter((b) => b.high != null).map((b) => ({ time: b.date, value: b.high as number })));
    const low = chart.addSeries(LineSeries, {
      color: dark ? "rgba(148,163,184,0.35)" : "rgba(100,116,139,0.35)",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    low.setData(bars.filter((b) => b.low != null).map((b) => ({ time: b.date, value: b.low as number })));
    const close = chart.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 2 });
    close.setData(bars.map((b) => ({ time: b.date, value: b.close as number })));

    for (const o of OVERLAYS) {
      if (o.key === "bb") {
        for (const k of ["bb_upper", "bb_mid", "bb_lower"]) {
          const pts = data.overlays[k];
          if (!pts) continue;
          const s = chart.addSeries(LineSeries, {
            color: o.color,
            lineWidth: 1,
            lineStyle: k === "bb_mid" ? LineStyle.Dotted : LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          s.setData(pts.map((p) => ({ time: p.date, value: p.value })));
        }
      } else if (data.overlays[o.key]) {
        const s = chart.addSeries(LineSeries, {
          color: o.color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        s.setData(data.overlays[o.key].map((p) => ({ time: p.date, value: p.value })));
      }
    }

    const vol = chart.addSeries(HistogramSeries, {
      priceScaleId: "vol",
      color: dark ? "rgba(148,163,184,0.3)" : "rgba(100,116,139,0.3)",
      priceFormat: { type: "volume" },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(bars.filter((b) => b.turnover != null).map((b) => ({ time: b.date, value: b.turnover as number })));
    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [data, resolvedTheme]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <Button key={r.key} size="xs" variant={range === r.key ? "secondary" : "ghost"} onClick={() => setRange(r.key)}>
              {r.label}
            </Button>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap gap-1">
          {OVERLAYS.map((o) => {
            const on = active.includes(o.key);
            return (
              <Button
                key={o.key}
                size="xs"
                variant={on ? "outline" : "ghost"}
                onClick={() => setActive((a) => (on ? a.filter((x) => x !== o.key) : [...a, o.key]))}
                className={cn(!on && "text-muted-foreground")}
              >
                <span className="size-2 rounded-full" style={{ background: o.color }} />
                {o.label}
              </Button>
            );
          })}
        </div>
      </div>
      {error && <ErrorBox error={error} />}
      {isLoading && !data && <Skeleton className="h-[380px] w-full" />}
      {data?.message && <p className="flex h-[380px] items-center justify-center text-sm text-muted-foreground">{data.message}</p>}
      {data && !data.message && <div ref={box} className="h-[380px] w-full" aria-label={`${symbol} fiyat grafiği`} />}
      <Notes notes={[data?.note]} />
    </div>
  );
}

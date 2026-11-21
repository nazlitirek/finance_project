"use client";

import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { fetcher } from "@/lib/api";
import { price } from "@/lib/format";

type Triggered = {
  items: { id: number; symbol: string; condition: "above" | "below"; target_price: number; triggered_price: number }[];
  server_time: string;
};

const POLL_MS = 60_000;

/** Tetiklenen fiyat alarmlarını düzenli sorgular; uygulama içi bildirim ve (izin varsa) tarayıcı bildirimi gösterir.
 * Çalışması için backend'in ve bu sekmenin açık olması gerekir. */
export function AlertNotifier() {
  const since = useRef<string | null>(null);

  useEffect(() => {
    let stopped = false;
    since.current = new Date().toISOString(); // sadece bu sekme açıldıktan sonra tetiklenenler
    async function poll() {
      try {
        const from = since.current ?? new Date().toISOString();
        const res = await fetcher<Triggered>(`/alerts/triggered?since=${encodeURIComponent(from)}`);
        since.current = res.server_time;
        for (const a of res.items) {
          const text = `${a.symbol} ${a.condition === "above" ? "üzerine çıktı" : "altına indi"}: hedef ${price(
            a.target_price,
          )}, kapanış ${price(a.triggered_price)}`;
          toast.info(`Fiyat alarmı: ${text}`);
          if (typeof Notification !== "undefined" && Notification.permission === "granted") {
            new Notification("BIST Intelligence fiyat alarmı", { body: text });
          }
        }
      } catch {
        // backend kapalıysa sessizce bir sonraki denemeyi bekle
      }
    }
    const id = setInterval(() => !stopped && poll(), POLL_MS);
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, []);

  return null;
}

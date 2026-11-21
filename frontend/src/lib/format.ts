// Türkçe sayı, tarih ve etiket biçimlendirme.

const nf = (min: number, max: number) =>
  new Intl.NumberFormat("tr-TR", { minimumFractionDigits: min, maximumFractionDigits: max });

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function num(v: unknown, digits = 2): string {
  return isNum(v) ? nf(0, digits).format(v) : "—";
}

export function price(v: unknown): string {
  return isNum(v) ? `${nf(2, 2).format(v)} TL` : "—";
}

/** Oran → yüzde: 0.1478 → %14,78 */
export function pct(v: unknown, digits = 1, fromRatio = true): string {
  if (!isNum(v)) return "—";
  const x = fromRatio ? v * 100 : v;
  return `${x < 0 ? "-" : ""}%${nf(digits, digits).format(Math.abs(x))}`;
}

export function signedPct(v: unknown, digits = 2): string {
  if (!isNum(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  return `${sign}%${nf(digits, digits).format(Math.abs(v))}`;
}

/** Büyük TL tutarları: 1.478.000.000.000 → 1.478,0 milyar TL */
export function money(v: unknown): string {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e12) return `${nf(1, 2).format(v / 1e12)} trilyon TL`;
  if (a >= 1e9) return `${nf(1, 1).format(v / 1e9)} milyar TL`;
  if (a >= 1e6) return `${nf(1, 1).format(v / 1e6)} milyon TL`;
  return `${nf(0, 0).format(v)} TL`;
}

export function multiple(v: unknown): string {
  return isNum(v) ? `${nf(2, 2).format(v)}x` : "—";
}

export function date(v: unknown): string {
  if (!v || typeof v !== "string") return "—";
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString("tr-TR", { day: "2-digit", month: "short", year: "numeric" });
}

export function dateTime(v: unknown): string {
  if (!v || typeof v !== "string") return "—";
  const d = new Date(v);
  return Number.isNaN(d.getTime())
    ? v
    : d.toLocaleString("tr-TR", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Birim koduna göre değer gösterimi (backend Metric.unit) */
export function byUnit(v: unknown, unit?: string | null): string {
  switch (unit) {
    case "%":
      return pct(v, 2);
    case "TL":
      return isNum(v) && Math.abs(v) >= 1e6 ? money(v) : price(v);
    case "x":
      return multiple(v);
    case "gün":
      return isNum(v) ? `${nf(0, 0).format(v)} gün` : "—";
    case "ratio":
      return num(v, 3);
    default:
      return num(v, 2);
  }
}

export const MODULE_TR: Record<string, string> = {
  technical: "Teknik analiz",
  fundamental: "Temel analiz",
  financial_health: "Finansal sağlık",
  valuation: "Değerleme",
  sector: "Sektör karşılaştırması",
  news: "Haber ve KAP",
  risk: "Risk",
};

export const LABEL_TR: Record<string, string> = { strong: "Güçlü", neutral: "Nötr", weak: "Zayıf" };

export const TREND_TR: Record<string, string> = { up: "Yükseliş", down: "Düşüş", sideways: "Yatay" };
export const MOMENTUM_TR: Record<string, string> = { strong: "Güçlü", weak: "Zayıf", neutral: "Nötr" };
export const RSI_TR: Record<string, string> = { overbought: "Aşırı alım", oversold: "Aşırı satım", normal: "Normal" };
export const VOLUME_TR: Record<string, string> = { supportive: "Destekliyor", weak: "Zayıf", neutral: "Nötr" };
export const VOLATILITY_TR: Record<string, string> = { high: "Yüksek", low: "Düşük", normal: "Normal" };
export const DIRECTION_TR: Record<string, string> = {
  positive: "Olumlu",
  negative: "Olumsuz",
  neutral: "Nötr",
  mixed: "Karışık",
};
export const IMPORTANCE_TR: Record<string, string> = { low: "Düşük", medium: "Orta", high: "Yüksek" };
export const HORIZON_TR: Record<string, string> = { short: "Kısa vade", medium: "Orta vade", long: "Uzun vade" };

export function changeClass(v: unknown): string {
  if (!isNum(v) || v === 0) return "text-muted-foreground";
  return v > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400";
}

export function scoreClass(score: unknown): string {
  if (!isNum(score)) return "text-muted-foreground";
  if (score >= 65) return "text-emerald-600 dark:text-emerald-400";
  if (score < 40) return "text-red-600 dark:text-red-400";
  return "text-amber-600 dark:text-amber-400";
}

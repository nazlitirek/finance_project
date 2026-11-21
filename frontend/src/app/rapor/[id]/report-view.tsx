"use client";

import { Download } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";

import { ErrorBox, LabelBadge, Loading, Notes, ScoreValue, Section } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { API_URL } from "@/lib/api";
import { MODULE_TR, dateTime, pct } from "@/lib/format";

type Sec = { text: string; evidence: string[]; data_gaps: string[] };
type Report = {
  id: number; symbol: string; created_at: string; status: string; model: string | null; error: string | null;
  overall_score: number | null; overall_label: string | null; data_coverage: number | null;
  data_as_of: { price_date?: string; financial_period?: string; generated_at?: string } | null;
  sources: string[] | null;
  scores: { module: string; score: number | null; reliability: number; label: string | null; details: { meaning?: string } }[];
  report: (Record<string, Sec | string[] | unknown> & { policy_warnings?: string[]; unverified_evidence?: string[] }) | null;
  analysis: { name: string; sector: string | null; price: number | null } | null;
  note: string;
};

const SECTIONS: [string, string][] = [
  ["company_overview", "Şirket hakkında"],
  ["general_assessment", "Genel değerlendirme"],
  ["technical", "Teknik analiz"],
  ["fundamental", "Temel analiz"],
  ["financial_health", "Finansal sağlık"],
  ["valuation", "Şirket değerlemesi"],
  ["sector", "Sektör karşılaştırması"],
  ["news_kap", "Haber ve KAP analizi"],
  ["risk", "Risk analizi"],
  ["short_term", "Kısa vadeli görünüm"],
  ["medium_term", "Orta vadeli görünüm"],
  ["long_term", "Uzun vadeli görünüm"],
];
const LISTS: [string, string][] = [
  ["positives", "Olumlu faktörler"],
  ["negatives", "Olumsuz faktörler"],
  ["uncertainties", "Önemli belirsizlikler"],
  ["contradictions", "Çelişkili göstergeler"],
];

function SectionBlock({ title, s }: { title: string; s?: Sec }) {
  if (!s) return null;
  return (
    <Section title={title}>
      <p className="text-sm leading-relaxed whitespace-pre-line">{s.text}</p>
      {s.evidence?.length > 0 && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-muted-foreground">Dayanılan veriler ({s.evidence.length})</summary>
          <ul className="mt-1 list-inside list-disc font-mono text-muted-foreground">
            {s.evidence.map((e) => <li key={e}>{e}</li>)}
          </ul>
        </details>
      )}
      {s.data_gaps?.length > 0 && (
        <div className="mt-2 text-xs text-amber-700 dark:text-amber-400">Eksik veri: {s.data_gaps.join(" · ")}</div>
      )}
    </Section>
  );
}

export function ReportView() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useSWR<Report>(`/reports/${id}`);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading rows={8} />;
  const r = data.report ?? {};
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Link href={`/hisse/${data.symbol}`} className="font-mono text-2xl font-bold hover:underline">{data.symbol}</Link>
            <Badge variant="outline">AI analiz raporu #{data.id}</Badge>
          </div>
          <p className="text-muted-foreground">{data.analysis?.name}</p>
          <p className="text-xs text-muted-foreground">
            Oluşturulma: {dateTime(data.created_at)} · Model: {data.model ?? "—"} · Fiyat tarihi: {data.data_as_of?.price_date ?? "—"} ·
            Finansal dönem: {data.data_as_of?.financial_period ?? "—"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {data.status === "completed" && (
            <a
              href={`${API_URL}/reports/${data.id}/pdf`}
              download
              className={buttonVariants({ variant: "outline" })}
            >
              <Download /> PDF indir
            </a>
          )}
          <ScoreValue score={data.overall_score} className="text-4xl" />
          <LabelBadge label={data.overall_label} />
        </div>
      </div>
      <Notes notes={[data.note, `Veri kapsamı: ${pct(data.data_coverage, 0)}. Kaynaklar: ${(data.sources ?? []).join(", ")}.`]} />
      {data.status !== "completed" && <ErrorBox error={new Error(`Rapor tamamlanamadı: ${data.error ?? data.status}`)} />}
      {(r.policy_warnings?.length ?? 0) > 0 && (
        <ErrorBox error={new Error(`Raporda denetimden geçmeyen ifadeler var: ${r.policy_warnings!.join("; ")}`)} />
      )}
      {(r.unverified_evidence?.length ?? 0) > 0 && (
        <ErrorBox error={new Error(`Girdide doğrulanamayan veriler: ${r.unverified_evidence!.join("; ")}`)} />
      )}
      <Card>
        <CardContent className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
          {data.scores.map((s) => (
            <div key={s.module} className="rounded-lg border p-2" title={s.details?.meaning}>
              <div className="text-xs text-muted-foreground">{MODULE_TR[s.module]}</div>
              <ScoreValue score={s.score} className="text-xl" />
              {s.module === "risk" && <div className="text-[11px] text-muted-foreground">100 = düşük risk</div>}
            </div>
          ))}
        </CardContent>
      </Card>
      {data.status === "completed" && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            {SECTIONS.map(([k, t]) => <SectionBlock key={k} title={t} s={r[k] as Sec | undefined} />)}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {LISTS.map(([k, t]) => {
              const list = (r[k] as string[] | undefined) ?? [];
              return (
                <Section key={k} title={t}>
                  {list.length ? (
                    <ul className="list-inside list-disc space-y-1 text-sm">{list.map((x) => <li key={x}>{x}</li>)}</ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">Yok.</p>
                  )}
                </Section>
              );
            })}
          </div>
          <SectionBlock title="Genel sonuç" s={r.conclusion as Sec | undefined} />
        </>
      )}
      <p className="text-xs text-muted-foreground">
        Bu rapor yatırım tavsiyesi değildir. Puanlar formüllerle hesaplanmış, yapay zekâ yalnızca yorumlamıştır.
      </p>
    </div>
  );
}

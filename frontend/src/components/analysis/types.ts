export type Metric = {
  code: string;
  name: string;
  value: number | null;
  previous?: number | null;
  previous_label?: string | null;
  formula?: string | null;
  unit?: string | null;
  signal?: "positive" | "negative" | "neutral" | null;
  comment?: string | null;
  sector_median?: number | null;
};

export type ModuleResult = {
  module: string;
  score: number | null;
  label: string | null;
  reliability: number;
  as_of: string | null;
  meaning: string;
  components: Record<string, number | null>;
  metrics: Metric[];
  assessments: Record<string, unknown>;
  notes: string[];
  extra: Record<string, unknown>;
};

export type Analysis = {
  symbol: string;
  name: string;
  sector: string | null;
  profile: string;
  price: number | null;
  price_date: string | null;
  financial_period: string | null;
  modules: Record<string, ModuleResult>;
  overall: {
    score: number | null;
    label: string | null;
    label_tr: string | null;
    coverage: number;
    missing_modules: string[];
    weights: Record<string, number>;
    note: string | null;
    disclaimer: string;
  };
};

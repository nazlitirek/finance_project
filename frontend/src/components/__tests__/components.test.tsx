// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { ScoreGrid } from "@/components/analysis/parts";
import type { ModuleResult } from "@/components/analysis/types";
import { ErrorBox, LabelBadge, Notes } from "@/components/common";
import { StockSearch } from "@/components/stock-search";

afterEach(cleanup);

function withSWR(ui: React.ReactNode, fetcher: (k: string) => Promise<unknown>) {
  return render(<SWRConfig value={{ fetcher, dedupingInterval: 0, provider: () => new Map() }}>{ui}</SWRConfig>);
}

describe("StockSearch", () => {
  it("yazınca arar, klavyeyle seçilen hisseyi döndürür", async () => {
    const fetcher = vi.fn(async (k: string) => {
      expect(k).toContain("/stocks/search?q=");
      return [
        { symbol: "THYAO", name: "TÜRK HAVA YOLLARI A.O.", sector: null, instrument_type: "equity" },
        { symbol: "PGSUS", name: "PEGASUS", sector: null, instrument_type: "equity" },
      ];
    });
    const onSelect = vi.fn();
    withSWR(<StockSearch onSelect={onSelect} />, fetcher);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Hisse ara"), "hava");
    await screen.findByText("PEGASUS");
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ symbol: "PGSUS" }));
    expect(fetcher.mock.calls.at(-1)?.[0]).toContain("q=hava");
  });

  it("sonuç yoksa bunu söyler", async () => {
    withSWR(<StockSearch onSelect={vi.fn()} />, async () => []);
    await userEvent.setup().type(screen.getByLabelText("Hisse ara"), "zzz");
    expect(await screen.findByText("Sonuç bulunamadı.")).toBeTruthy();
  });

  it("backend hatasını gösterir", async () => {
    withSWR(<StockSearch onSelect={vi.fn()} />, async () => {
      throw new Error("Backend'e bağlanılamadı.");
    });
    await userEvent.setup().type(screen.getByLabelText("Hisse ara"), "thy");
    await waitFor(() => expect(screen.getByText("Backend'e bağlanılamadı.")).toBeTruthy());
  });
});

describe("ScoreGrid", () => {
  const mod = (score: number | null): ModuleResult => ({
    module: "x", score, label: null, reliability: 0.8, as_of: null, meaning: "", components: {}, metrics: [],
    assessments: {}, notes: [], extra: {},
  });

  it("puanı olmayan modülde uydurma yapmaz, risk yönünü açıklar", () => {
    render(<ScoreGrid modules={{ technical: mod(62.2), sector: mod(null), risk: mod(70) }} />);
    expect(screen.getByText("62.2")).toBeTruthy();
    // 7 modülün hepsi gösterilir; verilmeyen 5 modül "Veri yetersiz" olur
    expect(screen.getAllByText("Veri yetersiz")).toHaveLength(5);
    expect(screen.getByText("100 = düşük risk")).toBeTruthy();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});

describe("ortak bileşenler", () => {
  it("hata kutusu mesajı gösterir", () => {
    render(<ErrorBox error={new Error("Veritabanına ulaşılamıyor.")} />);
    expect(screen.getByText("Veritabanına ulaşılamıyor.")).toBeTruthy();
  });

  it("boş notları göstermez, sınıf etiketini Türkçe yazar", () => {
    const { container } = render(<Notes notes={[null, undefined, ""]} />);
    expect(container.innerHTML).toBe("");
    render(<LabelBadge label="strong" />);
    expect(screen.getByText("Güçlü")).toBeTruthy();
    render(<LabelBadge label={null} />);
    expect(screen.getByText("Sınıf yok")).toBeTruthy();
  });
});

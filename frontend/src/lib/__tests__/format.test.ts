import { describe, expect, it } from "vitest";

import { byUnit, money, pct, price, signedPct } from "../format";

describe("format", () => {
  it("Türkçe fiyat ve yüzde", () => {
    expect(price(329)).toBe("329,00 TL");
    expect(pct(0.1478)).toBe("%14,8");
    expect(pct(-0.305)).toBe("-%30,5");
    expect(signedPct(0.23)).toBe("+%0,23");
    expect(signedPct(-2.36)).toBe("-%2,36");
    expect(signedPct(0)).toBe("%0,00");
  });

  it("büyük tutarlar okunur", () => {
    expect(money(1_478_000_000_000)).toBe("1,48 trilyon TL");
    expect(money(146_200_000_000)).toBe("146,2 milyar TL");
    expect(money(-4_967_000_000)).toBe("-5,0 milyar TL");
    expect(money(950)).toBe("950 TL");
  });

  it("eksik değer tire olur, uydurulmaz", () => {
    for (const f of [price, pct, signedPct, money]) {
      expect(f(null)).toBe("—");
      expect(f(Number.NaN)).toBe("—");
    }
    expect(byUnit(undefined, "%")).toBe("—");
  });

  it("birime göre gösterim", () => {
    expect(byUnit(0.25, "%")).toBe("%25,00");
    expect(byUnit(3.105, "x")).toBe("3,11x");
    expect(byUnit(18.5, "gün")).toBe("19 gün");
  });
});

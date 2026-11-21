import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiPost, fetcher } from "../api";

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("backend hata mesajını kullanıcıya iletir", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "x", message: "Hisse bulunamadı." }), { status: 404 })));
    await expect(fetcher("/stocks/YOK")).rejects.toMatchObject({ message: "Hisse bulunamadı.", status: 404 });
  });

  it("bağlantı hatasında anlaşılır mesaj", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err: unknown = await fetcher("/health").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toContain("Backend'e bağlanılamadı");
  });

  it("POST gövdesi JSON gönderilir, 204 boş döner", async () => {
    const f = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", f);
    await expect(apiPost("/watchlist", { symbol: "THYAO" })).resolves.toBeUndefined();
    const [, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ symbol: "THYAO" }));
  });
});

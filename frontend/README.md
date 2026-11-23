# BIST Intelligence — frontend

Next.js 16 + React 19 + TypeScript + Tailwind 4 + shadcn/ui (Base UI) + SWR.

Kurulum ve çalıştırma için kök klasördeki [README.md](../README.md) dosyasına bakın.

```powershell
npm ci
copy .env.example .env.local
npm run dev        # http://localhost:3000
npm test           # birim ve bileşen testleri
npm run build      # üretim derlemesi
```

Frontend sadece kendi backend'imize (`NEXT_PUBLIC_API_URL`, varsayılan `http://127.0.0.1:8000/api`) bağlanır.
Not: Windows'ta `localhost` yerine `127.0.0.1` kullanılır; `localhost` her istekte ~2 sn gecikmeye yol açıyordu.

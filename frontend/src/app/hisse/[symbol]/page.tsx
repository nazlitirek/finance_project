import { Suspense } from "react";

import { Loading } from "@/components/common";

import { StockView } from "./stock-view";

export default function StockPage() {
  return (
    <Suspense fallback={<Loading rows={6} />}>
      <StockView />
    </Suspense>
  );
}

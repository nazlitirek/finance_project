import { Suspense } from "react";

import { Loading } from "@/components/common";

import { PortfolioView } from "./portfolio-view";

export default function PortfolioPage() {
  return (
    <Suspense fallback={<Loading rows={6} />}>
      <PortfolioView />
    </Suspense>
  );
}

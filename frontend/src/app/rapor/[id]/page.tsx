import { Suspense } from "react";

import { Loading } from "@/components/common";

import { ReportView } from "./report-view";

export default function ReportPage() {
  return (
    <Suspense fallback={<Loading rows={8} />}>
      <ReportView />
    </Suspense>
  );
}

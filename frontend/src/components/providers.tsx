"use client";

import { ThemeProvider } from "next-themes";
import { SWRConfig } from "swr";

import { AlertNotifier } from "@/components/alert-notifier";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { fetcher } from "@/lib/api";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
      <SWRConfig value={{ fetcher, revalidateOnFocus: false, shouldRetryOnError: false }}>
        <TooltipProvider>
          {children}
          <AlertNotifier />
          <Toaster richColors position="bottom-right" />
        </TooltipProvider>
      </SWRConfig>
    </ThemeProvider>
  );
}

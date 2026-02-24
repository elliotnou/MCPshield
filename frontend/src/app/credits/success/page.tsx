"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Coins, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCredits } from "@/lib/use-credits";

export default function CreditSuccessPage() {
  const router = useRouter();
  const { purchaseCredits, balance, fetchBalance } = useCredits();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");

  useEffect(() => {
    let done = false;
    async function addCredits() {
      try {
        // Add 100 credits after successful Flowglad checkout
        await purchaseCredits(100, `flowglad_${Date.now()}`);
        await fetchBalance();
        if (!done) setStatus("success");
      } catch {
        if (!done) setStatus("error");
      }
    }
    addCredits();
    return () => { done = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="max-w-md w-full text-center space-y-6 p-8">
        {status === "loading" && (
          <>
            <Loader2 className="w-12 h-12 text-primary animate-spin mx-auto" />
            <h1 className="text-xl font-bold text-foreground">Processing payment...</h1>
            <p className="text-sm text-muted-foreground">Adding credits to your account</p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="w-16 h-16 rounded-2xl bg-emerald-500/20 flex items-center justify-center mx-auto">
              <Check className="w-8 h-8 text-emerald-400" />
            </div>
            <h1 className="text-xl font-bold text-foreground">Credits Added!</h1>
            <div className="flex items-center justify-center gap-2 text-lg">
              <Coins className="w-5 h-5 text-amber-400" />
              <span className="font-bold text-foreground">{balance} credits</span>
            </div>
            <p className="text-sm text-muted-foreground">
              100 credits have been added to your account. You can now generate MCP servers.
            </p>
            <Button
              onClick={() => router.push("/adapter/generate")}
              className="btn-gradient rounded-full px-8"
            >
              Continue to Generator
            </Button>
          </>
        )}

        {status === "error" && (
          <>
            <h1 className="text-xl font-bold text-red-400">Something went wrong</h1>
            <p className="text-sm text-muted-foreground">
              Your payment was received but we had trouble adding credits. Please contact support.
            </p>
            <Button variant="outline" onClick={() => router.push("/adapter/generate")}>
              Go Back
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

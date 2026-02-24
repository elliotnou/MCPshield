"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8080";
const DEDALUS_USER = process.env.NEXT_PUBLIC_USER || "default";

export interface CreditInfo {
  user: string;
  balance: number;
  total_purchased: number;
  total_spent: number;
  cost_per_tool: number;
}

export interface PricingInfo {
  pack_size: number;
  pack_price_cents: number;
  pack_price_display: string;
  cost_per_tool: number;
}

export function useCredits() {
  const [credits, setCredits] = useState<CreditInfo | null>(null);
  const [pricing, setPricing] = useState<PricingInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchBalance = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/credits/${DEDALUS_USER}`);
      if (res.ok) {
        const data = await res.json();
        setCredits(data);
      }
    } catch {
      // silently fail — balance will show as null
    }
  }, []);

  const fetchPricing = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/credits/pricing`);
      if (res.ok) {
        setPricing(await res.json());
      }
    } catch {
      // silently fail
    }
  }, []);

  const purchaseCredits = useCallback(async (amount: number = 100, paymentId?: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/credits/purchase`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user: DEDALUS_USER,
          credits: amount,
          payment_id: paymentId || `test_${Date.now()}`,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Purchase failed");
      }
      const data = await res.json();
      setCredits((prev) => prev ? { ...prev, balance: data.balance } : null);
      setLoading(false);
      return data;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setLoading(false);
      throw e;
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchBalance();
    fetchPricing();
  }, [fetchBalance, fetchPricing]);

  return {
    credits,
    pricing,
    loading,
    error,
    balance: credits?.balance ?? 0,
    fetchBalance,
    purchaseCredits,
  };
}

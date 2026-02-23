"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { StepHeader } from "@/components/adapter/StepHeader";
import { Button } from "@/components/ui/button";
import { usePipeline } from "@/lib/pipeline-context";
import { ArrowRight, ArrowLeft, Shield, Lock, Unlock, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface LocalPolicy {
  name: string;
  method: string;
  path: string;
  safetyLevel: "read" | "write" | "destructive";
  autoExecute: boolean;
  rateLimitQpm: number;
}

const SAFETY_COLORS: Record<string, string> = {
  read: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  write: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  destructive: "bg-red-500/15 text-red-400 border-red-500/30",
};

export default function PolicyPage() {
  const router = useRouter();
  const { tools, updatePolicies, loading } = usePipeline();
  const [policies, setPolicies] = useState<LocalPolicy[]>([]);

  useEffect(() => {
    if (tools.length && !policies.length) {
      setPolicies(
        tools.map((t) => {
          const ep = t.endpoints[0];
          return {
            name: t.name,
            method: ep?.method || "GET",
            path: ep?.path || "",
            safetyLevel: t.safety as LocalPolicy["safetyLevel"],
            autoExecute: t.safety === "read",
            rateLimitQpm: t.safety === "read" ? 60 : t.safety === "write" ? 30 : 10,
          };
        })
      );
    }
  }, [tools, policies.length]);

  if (!tools.length) {
    return (
      <>
        <StepHeader currentStep="policy" title="Policy Configuration" description="" />
        <div className="flex flex-col items-center py-20 gap-4">
          <AlertCircle className="w-8 h-8 text-muted-foreground" />
          <p className="text-muted-foreground">No tools loaded. Go back to Ingest first.</p>
          <Button variant="outline" onClick={() => router.push("/adapter/ingest")}>Go to Ingest</Button>
        </div>
      </>
    );
  }

  const updatePolicy = (idx: number, updates: Partial<LocalPolicy>) => {
    setPolicies((prev) => prev.map((p, i) => (i === idx ? { ...p, ...updates } : p)));
  };

  const handleContinue = async () => {
    await updatePolicies(
      policies.map((p) => ({
        name: p.name,
        safety: p.safetyLevel,
        auto_execute: p.autoExecute,
        rate_limit_qpm: p.rateLimitQpm,
      }))
    );
    router.push("/adapter/generate");
  };

  return (
    <>
      <StepHeader
        currentStep="policy"
        title="Policy Configuration"
        description="Configure safety rules, rate limits, and execution policies for each tool"
      />

      <div className="space-y-3">
        <div className="grid grid-cols-[1fr_120px_140px_100px_80px] gap-3 px-4 text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
          <span>Tool</span>
          <span>Safety Level</span>
          <span>Execution</span>
          <span>Rate Limit</span>
          <span></span>
        </div>

        {policies.map((tool, idx) => (
          <div key={tool.name} className="card-glass p-4 grid grid-cols-[1fr_120px_140px_100px_80px] gap-3 items-center">
            <div className="min-w-0">
              <p className="text-sm font-bold text-foreground truncate">{tool.name}</p>
              <p className="text-[11px] text-muted-foreground font-mono truncate">{tool.method} {tool.path}</p>
            </div>

            <select
              value={tool.safetyLevel}
              onChange={(e) => updatePolicy(idx, { safetyLevel: e.target.value as LocalPolicy["safetyLevel"] })}
              className={cn(
                "h-8 rounded-md px-2 text-[11px] font-bold border cursor-pointer bg-transparent focus:outline-none focus:ring-1 focus:ring-primary/30",
                SAFETY_COLORS[tool.safetyLevel]
              )}
            >
              <option value="read">Read</option>
              <option value="write">Write</option>
              <option value="destructive">Destructive</option>
            </select>

            <button
              onClick={() => updatePolicy(idx, { autoExecute: !tool.autoExecute })}
              className={cn(
                "h-8 rounded-md px-3 text-[11px] font-semibold border flex items-center gap-1.5 transition-colors cursor-pointer",
                tool.autoExecute
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  : "bg-amber-500/10 text-amber-400 border-amber-500/20"
              )}
            >
              {tool.autoExecute ? <Unlock className="w-3 h-3" /> : <Lock className="w-3 h-3" />}
              {tool.autoExecute ? "Auto Execute" : "Needs Confirm"}
            </button>

            <div className="flex items-center gap-1">
              <input
                type="number"
                value={tool.rateLimitQpm}
                onChange={(e) => updatePolicy(idx, { rateLimitQpm: parseInt(e.target.value) || 0 })}
                className="w-16 h-8 rounded-md bg-card border border-border px-2 text-xs text-foreground font-mono text-center focus:outline-none focus:ring-1 focus:ring-primary/30"
                min={1}
                max={1000}
              />
              <span className="text-[10px] text-muted-foreground">/min</span>
            </div>

            <div className="flex justify-end">
              <Shield className={cn(
                "w-4 h-4",
                tool.safetyLevel === "read" ? "text-emerald-400" :
                tool.safetyLevel === "write" ? "text-amber-400" : "text-red-400"
              )} />
            </div>
          </div>
        ))}

        <div className="card-glass p-4 mt-4">
          <h4 className="text-xs font-bold text-foreground mb-2">Policy Summary</h4>
          <div className="flex items-center gap-6 text-xs text-muted-foreground">
            <span>Auto-execute: <strong className="text-foreground">{policies.filter((p) => p.autoExecute).length}</strong></span>
            <span>Needs confirmation: <strong className="text-foreground">{policies.filter((p) => !p.autoExecute).length}</strong></span>
            <span>Read: <strong className="text-emerald-400">{policies.filter((p) => p.safetyLevel === "read").length}</strong></span>
            <span>Write: <strong className="text-amber-400">{policies.filter((p) => p.safetyLevel === "write").length}</strong></span>
            <span>Destructive: <strong className="text-red-400">{policies.filter((p) => p.safetyLevel === "destructive").length}</strong></span>
          </div>
        </div>

        <div className="flex items-center justify-between pt-4">
          <Button variant="ghost" onClick={() => router.push("/adapter/schema")} className="text-muted-foreground">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
          <Button onClick={handleContinue} disabled={loading} className="btn-gradient rounded-full px-6 relative z-10">
            <span>Generate MCP Server</span> <ArrowRight className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </>
  );
}

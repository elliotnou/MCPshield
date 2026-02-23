"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { StepHeader } from "@/components/adapter/StepHeader";
import { Button } from "@/components/ui/button";
import { usePipeline } from "@/lib/pipeline-context";
import { cn } from "@/lib/utils";
import {
  ArrowRight, ArrowLeft, Search, Tag, Globe, AlertCircle,
  ShieldCheck, ShieldAlert, ShieldQuestion, Loader2, ToggleLeft, ToggleRight,
} from "lucide-react";

const METHOD_COLORS: Record<string, string> = {
  GET: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  POST: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  PUT: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  DELETE: "bg-red-500/15 text-red-400 border-red-500/30",
  PATCH: "bg-purple-500/15 text-purple-400 border-purple-500/30",
};

const CLASS_BADGE: Record<string, { icon: typeof ShieldCheck; color: string; label: string }> = {
  safe: { icon: ShieldCheck, color: "text-emerald-400 bg-emerald-500/15 border-emerald-500/25", label: "Safe" },
  unsafe: { icon: ShieldAlert, color: "text-red-400 bg-red-500/15 border-red-500/25", label: "Blocked" },
  conditional: { icon: ShieldQuestion, color: "text-amber-400 bg-amber-500/15 border-amber-500/25", label: "Conditional" },
  unknown: { icon: ShieldQuestion, color: "text-muted-foreground bg-muted/50 border-border/50", label: "Unknown" },
};

export default function DiscoverPage() {
  const router = useRouter();
  const { tools, classifications, spec, runDiscover, confirmDiscovery, loading, error } = usePipeline();
  const [filter, setFilter] = useState("");
  const [selectedPolicy, setSelectedPolicy] = useState("moderate");
  // Track which tools are enabled (by name). Initialize from classifications.
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});

  // Initialize enabled state from classifications
  useEffect(() => {
    if (!tools.length) return;
    const classMap = new Map(
      (classifications?.classifications || []).map((c) => [c.name, c])
    );
    const init: Record<string, boolean> = {};
    for (const t of tools) {
      const cls = classMap.get(t.name);
      // Default: enabled if expose is true or "review", disabled if expose is false
      init[t.name] = cls ? cls.expose !== false : true;
    }
    setEnabled(init);
  }, [tools, classifications]);

  const toggleTool = useCallback((name: string) => {
    setEnabled((prev) => ({ ...prev, [name]: !prev[name] }));
  }, []);

  const enabledCount = Object.values(enabled).filter(Boolean).length;
  const disabledCount = tools.length - enabledCount;

  if (!tools.length) {
    return (
      <>
        <StepHeader currentStep="discover" title="Discovered Endpoints" description="" />
        <div className="flex flex-col items-center py-20 gap-4">
          <AlertCircle className="w-8 h-8 text-muted-foreground" />
          <p className="text-muted-foreground">No endpoints loaded. Go back to Ingest and parse a spec first.</p>
          <Button variant="outline" onClick={() => router.push("/adapter/ingest")}>Go to Ingest</Button>
        </div>
      </>
    );
  }

  const classMap = new Map(
    (classifications?.classifications || []).map((c) => [c.name, c])
  );

  const filtered = tools.filter(
    (t) =>
      t.name.toLowerCase().includes(filter.toLowerCase()) ||
      t.description.toLowerCase().includes(filter.toLowerCase()) ||
      (t.endpoints[0]?.method || "").toLowerCase().includes(filter.toLowerCase())
  );

  const handleContinue = async () => {
    const allowedTools = tools.filter((t) => enabled[t.name]).map((t) => t.name);
    await confirmDiscovery(allowedTools);
    router.push("/adapter/schema");
  };

  return (
    <>
      <StepHeader
        currentStep="discover"
        title="Discovered Endpoints"
        description={spec ? `${spec.title} v${spec.version} — ${spec.base_url}` : "APIs extracted from your spec"}
      />

      <div className="space-y-6">
        {/* Summary bar */}
        <div className="card-glass p-4 flex items-center gap-6 flex-wrap">
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-primary" />
            <span className="text-sm font-bold text-foreground">{tools.length} tools discovered</span>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className="text-muted-foreground">{enabledCount} enabled</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-400" />
              <span className="text-muted-foreground">{disabledCount} disabled</span>
            </span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="text-xs h-7"
              onClick={() => setEnabled(Object.fromEntries(tools.map((t) => [t.name, true])))}
            >
              Enable All
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-xs h-7"
              onClick={() => {
                const init: Record<string, boolean> = {};
                for (const t of tools) {
                  const cls = classMap.get(t.name);
                  init[t.name] = cls ? cls.expose !== false : true;
                }
                setEnabled(init);
              }}
            >
              Reset
            </Button>
            <select
              value={selectedPolicy}
              onChange={(e) => setSelectedPolicy(e.target.value)}
              className="text-xs bg-card border border-border rounded-md px-2 py-1 text-foreground"
            >
              <option value="conservative">Conservative</option>
              <option value="moderate">Moderate</option>
              <option value="permissive">Permissive</option>
            </select>
            <Button
              variant="outline"
              size="sm"
              className="text-xs h-7"
              disabled={loading}
              onClick={() => runDiscover(selectedPolicy)}
            >
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : "Re-classify"}
            </Button>
          </div>
        </div>

        {/* Filter */}
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter tools..."
              className="w-full h-10 rounded-lg bg-card border border-border pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}

        {/* Tool list with classifications and toggles */}
        <div className="space-y-2">
          {filtered.map((tool) => {
            const ep = tool.endpoints[0];
            const cls = classMap.get(tool.name);
            const badge = CLASS_BADGE[cls?.classification || "unknown"];
            const BadgeIcon = badge.icon;
            const isEnabled = enabled[tool.name] ?? true;

            return (
              <div
                key={tool.name}
                className={cn(
                  "card-glass p-4 flex items-center gap-4 group transition-opacity",
                  !isEnabled && "opacity-40"
                )}
              >
                {/* Toggle */}
                <button
                  onClick={() => toggleTool(tool.name)}
                  className={cn(
                    "shrink-0 transition-colors",
                    isEnabled ? "text-primary" : "text-muted-foreground hover:text-foreground"
                  )}
                  title={isEnabled ? "Click to disable" : "Click to enable"}
                >
                  {isEnabled ? <ToggleRight className="w-6 h-6" /> : <ToggleLeft className="w-6 h-6" />}
                </button>

                {/* Method badge */}
                {ep && (
                  <span className={`px-2.5 py-1 rounded-md text-[11px] font-bold font-mono border shrink-0 ${METHOD_COLORS[ep.method] || "bg-muted text-muted-foreground"}`}>
                    {ep.method}
                  </span>
                )}

                {/* Name & path */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <code className="text-sm font-mono font-bold text-foreground truncate">{tool.name}</code>
                    {ep && <code className="text-xs font-mono text-muted-foreground truncate hidden sm:block">{ep.path}</code>}
                  </div>
                  <p className="text-xs text-muted-foreground truncate mt-0.5">{tool.description}</p>
                </div>

                {/* Classification badge */}
                {cls && (
                  <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-bold border shrink-0 ${badge.color}`}>
                    <BadgeIcon className="w-3 h-3" />
                    {badge.label}
                  </div>
                )}

                {/* Confidence */}
                {cls && (
                  <span className="text-[10px] font-mono text-muted-foreground shrink-0 w-10 text-right">
                    {Math.round(cls.confidence * 100)}%
                  </span>
                )}

                {/* Tags */}
                <div className="flex items-center gap-1.5 shrink-0">
                  {tool.tags.slice(0, 2).map((tag) => (
                    <span key={tag} className="flex items-center gap-0.5 text-[10px] text-muted-foreground px-1.5 py-0.5 rounded-full glass">
                      <Tag className="w-2.5 h-2.5" />
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Info about what happens next */}
        <div className="card-glass p-3 flex items-center gap-3">
          <ShieldCheck className="w-4 h-4 text-primary shrink-0" />
          <p className="text-xs text-muted-foreground">
            Only the <strong className="text-foreground">{enabledCount} enabled</strong> tools will proceed to Schema, Policy, and Code Generation.
            {disabledCount > 0 && <> <strong className="text-foreground">{disabledCount}</strong> tools will be excluded.</>}
          </p>
        </div>

        <div className="flex items-center justify-between pt-4">
          <Button variant="ghost" onClick={() => router.push("/adapter/ingest")} className="text-muted-foreground">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
          <Button
            onClick={handleContinue}
            disabled={loading || enabledCount === 0}
            className="btn-gradient rounded-full px-6 relative z-10"
          >
            {loading ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Confirming...</>
            ) : (
              <><span>Continue with {enabledCount} tools</span> <ArrowRight className="w-4 h-4" /></>
            )}
          </Button>
        </div>
      </div>
    </>
  );
}

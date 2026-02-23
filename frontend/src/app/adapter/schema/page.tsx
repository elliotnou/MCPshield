"use client";

import { useRouter } from "next/navigation";
import { StepHeader } from "@/components/adapter/StepHeader";
import { Button } from "@/components/ui/button";
import { usePipeline } from "@/lib/pipeline-context";
import { ArrowRight, ArrowLeft, Braces, Check, AlertCircle } from "lucide-react";

const METHOD_BADGE: Record<string, string> = {
  GET: "text-emerald-400",
  POST: "text-blue-400",
  DELETE: "text-red-400",
  PUT: "text-amber-400",
  PATCH: "text-purple-400",
};

export default function SchemaPage() {
  const router = useRouter();
  const { tools } = usePipeline();

  if (!tools.length) {
    return (
      <>
        <StepHeader currentStep="schema" title="Generated Schemas" description="" />
        <div className="flex flex-col items-center py-20 gap-4">
          <AlertCircle className="w-8 h-8 text-muted-foreground" />
          <p className="text-muted-foreground">No tools loaded. Go back to Ingest first.</p>
          <Button variant="outline" onClick={() => router.push("/adapter/ingest")}>Go to Ingest</Button>
        </div>
      </>
    );
  }

  return (
    <>
      <StepHeader
        currentStep="schema"
        title="Generated Schemas"
        description={`${tools.length} MCP tool schemas synthesized from discovered endpoints`}
      />

      <div className="space-y-4">
        {tools.map((tool) => {
          const ep = tool.endpoints[0];
          return (
            <div key={tool.name} className="card-glass p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Braces className="w-4 h-4 text-primary shrink-0" />
                  <div>
                    <h3 className="text-sm font-bold text-foreground">{tool.name}</h3>
                    <p className="text-xs text-muted-foreground">{tool.description}</p>
                  </div>
                </div>
                {ep && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className={`font-mono font-bold ${METHOD_BADGE[ep.method] || "text-muted-foreground"}`}>
                      {ep.method}
                    </span>
                    <code className="text-muted-foreground font-mono">{ep.path}</code>
                  </div>
                )}
              </div>

              {tool.params.length > 0 && (
                <div className="rounded-lg bg-background/50 border border-border/50 overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border/30">
                        <th className="text-left px-3 py-2 font-semibold text-muted-foreground">Parameter</th>
                        <th className="text-left px-3 py-2 font-semibold text-muted-foreground">Type</th>
                        <th className="text-left px-3 py-2 font-semibold text-muted-foreground">Required</th>
                        <th className="text-left px-3 py-2 font-semibold text-muted-foreground">Description</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tool.params.map((p) => (
                        <tr key={p.name} className="border-b border-border/20 last:border-0">
                          <td className="px-3 py-2 font-mono text-foreground">{p.name}</td>
                          <td className="px-3 py-2 text-primary font-mono">{p.json_type}</td>
                          <td className="px-3 py-2">
                            {p.required ? (
                              <span className="flex items-center gap-1 text-primary"><Check className="w-3 h-3" /> Yes</span>
                            ) : (
                              <span className="text-muted-foreground">No</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-muted-foreground">{p.description}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {tool.params.length === 0 && (
                <p className="text-xs text-muted-foreground italic px-1">No parameters</p>
              )}
            </div>
          );
        })}

        <div className="flex items-center justify-between pt-4">
          <Button variant="ghost" onClick={() => router.push("/adapter/discover")} className="text-muted-foreground">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
          <Button onClick={() => router.push("/adapter/policy")} className="btn-gradient rounded-full px-6 relative z-10">
            <span>Continue to Policy</span> <ArrowRight className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </>
  );
}

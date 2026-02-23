"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { StepHeader } from "@/components/adapter/StepHeader";
import { Button } from "@/components/ui/button";
import { usePipeline } from "@/lib/pipeline-context";
import { ArrowRight, ArrowLeft, Check, Loader2, TestTube, AlertCircle, FileCode, Copy, CheckCheck } from "lucide-react";

export default function TestPage() {
  const router = useRouter();
  const { testInfo, runTest, generated, loading: pipelineLoading } = usePipeline();
  const [fetched, setFetched] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!fetched && generated && !testInfo) {
      runTest().then(() => setFetched(true));
    }
  }, [generated, testInfo, fetched, runTest]);

  if (!generated) {
    return (
      <>
        <StepHeader currentStep="test" title="Contract Tests" description="" />
        <div className="flex flex-col items-center py-20 gap-4">
          <AlertCircle className="w-8 h-8 text-muted-foreground" />
          <p className="text-muted-foreground">No generated code. Go back to Generate first.</p>
          <Button variant="outline" onClick={() => router.push("/adapter/generate")}>Go to Generate</Button>
        </div>
      </>
    );
  }

  const copyRunCommand = () => {
    const dir = generated.output_dir || "./output";
    const cmd = `cd ${dir} && pip install -r requirements.txt && python test_server.py`;
    navigator.clipboard.writeText(cmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <>
      <StepHeader
        currentStep="test"
        title="Contract Tests"
        description="Auto-generated test suite for your MCP server"
      />

      <div className="space-y-6">
        {pipelineLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 text-primary animate-spin" />
            <span className="ml-2 text-sm text-muted-foreground">Loading test suite...</span>
          </div>
        )}

        {!pipelineLoading && testInfo && (
          <>
            {/* Summary card */}
            <div className="card-glass p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
                  <Check className="w-4 h-4 text-emerald-400" />
                </div>
                <div>
                  <p className="text-sm font-bold text-foreground">
                    {testInfo.test_count} tests generated
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Ready to run against your upstream API
                  </p>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={copyRunCommand} className="text-xs gap-1.5">
                {copied ? <CheckCheck className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {copied ? "Copied" : "Copy run command"}
              </Button>
            </div>

            {/* Test list */}
            <div className="space-y-1.5">
              {testInfo.test_names.map((name: string) => (
                <div
                  key={name}
                  className="flex items-center gap-3 px-4 py-3 rounded-lg border bg-card border-border/30"
                >
                  <div className="w-5 h-5 flex items-center justify-center shrink-0">
                    <TestTube className="w-4 h-4 text-muted-foreground" />
                  </div>
                  <span className="text-sm font-mono font-medium text-foreground">{name}()</span>
                </div>
              ))}
            </div>

            {/* How to run */}
            <div className="card-glass p-5 space-y-3">
              <div className="flex items-center gap-2">
                <FileCode className="w-4 h-4 text-primary" />
                <h4 className="text-sm font-bold text-foreground">Run tests locally</h4>
              </div>
              <p className="text-xs text-muted-foreground">
                Start your generated MCP server, then run the test suite against it:
              </p>
              <div className="bg-black/40 rounded-lg p-3 font-mono text-xs text-emerald-400 space-y-1">
                <p className="text-muted-foreground"># Terminal 1: Start the server</p>
                <p>cd {generated.output_dir || "./output"}</p>
                <p>pip install -r requirements.txt</p>
                <p>cp .env.example .env  <span className="text-muted-foreground"># add your API key</span></p>
                <p>python server.py</p>
                <p className="mt-3 text-muted-foreground"># Terminal 2: Run tests</p>
                <p>python test_server.py</p>
              </div>
            </div>

            {/* Test file preview */}
            {testInfo.test_file && (
              <details className="card-glass overflow-hidden">
                <summary className="px-5 py-3 cursor-pointer text-sm font-medium text-foreground hover:bg-white/5 transition-colors">
                  View test source ({testInfo.test_count} tests)
                </summary>
                <div className="border-t border-border/30">
                  <pre className="p-4 text-xs font-mono text-muted-foreground overflow-x-auto max-h-96">
                    <code>{testInfo.test_file}</code>
                  </pre>
                </div>
              </details>
            )}
          </>
        )}

        <div className="flex items-center justify-between pt-4">
          <Button variant="ghost" onClick={() => router.push("/adapter/generate")} className="text-muted-foreground">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
          <Button
            onClick={() => router.push("/adapter/deploy")}
            disabled={!testInfo}
            className="btn-gradient rounded-full px-6 relative z-10"
          >
            <span>Deploy</span> <ArrowRight className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </>
  );
}

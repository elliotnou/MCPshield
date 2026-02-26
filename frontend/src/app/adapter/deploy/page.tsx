"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { StepHeader } from "@/components/adapter/StepHeader";
import { Button } from "@/components/ui/button";
import { usePipeline } from "@/lib/pipeline-context";
import {
  ArrowLeft, Rocket, GitBranch, Check, Loader2, ExternalLink,
  Copy, Key, Terminal, AlertCircle,
} from "lucide-react";

export default function DeployPage() {
  const router = useRouter();
  const { deployInfo, runDeploy, generated, loading, error, dedalusUser } = usePipeline();
  const [copied, setCopied] = useState<string | null>(null);
  const [githubToken, setGithubToken] = useState("");

  if (!generated) {
    return (
      <>
        <StepHeader currentStep="deploy" title="Deploy to Production" description="" />
        <div className="flex flex-col items-center py-20 gap-4">
          <AlertCircle className="w-8 h-8 text-muted-foreground" />
          <p className="text-muted-foreground">No generated code. Complete the previous steps first.</p>
          <Button variant="outline" onClick={() => router.push("/adapter/generate")}>Go to Generate</Button>
        </div>
      </>
    );
  }

  const handleDeploy = async () => {
    if (!githubToken.trim()) return;
    await runDeploy(githubToken.trim());
  };

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  const envVars = deployInfo?.env_vars || {};

  return (
    <>
      <StepHeader
        currentStep="deploy"
        title="Deploy to Production"
        description="Push to GitHub and deploy to Dedalus with all required credentials"
      />

      <div className="space-y-6">
        {!deployInfo && !loading && (
          <div className="flex flex-col items-center justify-center py-16 space-y-6">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-[hsl(330_60%_55%)] to-[hsl(340_50%_45%)] flex items-center justify-center shadow-lg animate-pulse-glow">
              <Rocket className="w-8 h-8 text-primary-foreground" />
            </div>
            <div className="text-center space-y-2">
              <h3 className="text-lg font-bold text-foreground">Ready to deploy</h3>
              <p className="text-sm text-muted-foreground max-w-md">
                Enter your GitHub personal access token to create a repository under your account with the generated MCP server.
              </p>
            </div>

            {/* GitHub token input */}
            <div className="w-full max-w-md space-y-2">
              <label className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5" />
                GitHub Personal Access Token
              </label>
              <input
                type="password"
                value={githubToken}
                onChange={(e) => setGithubToken(e.target.value)}
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                className="w-full h-10 px-3 rounded-lg bg-background border border-border/50 text-sm font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-all"
              />
              <p className="text-[11px] text-muted-foreground">
                Needs <code className="text-primary/70">repo</code> scope.{" "}
                <a href="https://github.com/settings/tokens/new" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                  Create one here
                </a>
              </p>
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive max-w-md">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {error}
              </div>
            )}
            <Button onClick={handleDeploy} disabled={!githubToken.trim()} className="btn-gradient rounded-full px-8 h-12 relative z-10">
              <GitBranch className="w-4 h-4" />
              <span>Push to GitHub & Deploy</span>
            </Button>
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center py-16 space-y-6">
            <Loader2 className="w-12 h-12 text-primary animate-spin" />
            <div className="text-center space-y-2">
              <h3 className="text-lg font-bold text-foreground">Deploying...</h3>
              <p className="text-sm text-muted-foreground">Creating repository and pushing code to GitHub</p>
            </div>
            <div className="w-80 space-y-2">
              {["Creating GitHub repository...", "Pushing server code...", "Writing deployment manifest..."].map((step, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="w-3 h-3 animate-spin text-primary" />
                  {step}
                </div>
              ))}
            </div>
          </div>
        )}

        {deployInfo && (
          <div className="space-y-6">
            {/* Success banner */}
            <div className="card-glass p-5 flex items-center gap-4">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center shrink-0">
                <Check className="w-5 h-5 text-emerald-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold text-foreground">Repository created & code pushed</p>
                <div className="flex items-center gap-2 mt-1">
                  <code className="text-xs font-mono text-primary truncate">{deployInfo.repo_url}</code>
                  <a href={deployInfo.repo_url} target="_blank" rel="noopener noreferrer" className="shrink-0">
                    <ExternalLink className="w-3.5 h-3.5 text-muted-foreground hover:text-primary transition-colors" />
                  </a>
                </div>
              </div>
            </div>

            {/* Dedalus deploy instructions */}
            <div className="card-glass p-6 space-y-5">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
                  <Rocket className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">Deploy on Dedalus</h3>
                  <p className="text-[11px] text-muted-foreground">Follow these steps to deploy your MCP server</p>
                </div>
              </div>

              <ol className="space-y-4 text-sm">
                <li className="flex items-start gap-3">
                  <span className="w-6 h-6 rounded-full bg-primary/15 flex items-center justify-center text-xs font-bold text-primary shrink-0 mt-0.5">1</span>
                  <div>
                    <p className="font-medium text-foreground">Go to Dedalus Dashboard</p>
                    <a href={deployInfo.dashboard_url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline flex items-center gap-1 mt-0.5">
                      {deployInfo.dashboard_url} <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="w-6 h-6 rounded-full bg-primary/15 flex items-center justify-center text-xs font-bold text-primary shrink-0 mt-0.5">2</span>
                  <div>
                    <p className="font-medium text-foreground">Import from GitHub</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Click &quot;New Server&quot; → &quot;Import from GitHub&quot; → select <code className="text-primary">{deployInfo.repo_full_name}</code>
                    </p>
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="w-6 h-6 rounded-full bg-primary/15 flex items-center justify-center text-xs font-bold text-primary shrink-0 mt-0.5">3</span>
                  <div>
                    <p className="font-medium text-foreground">Configure Environment Variables</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Set these in the Dedalus dashboard → Environment Variables</p>
                  </div>
                </li>
              </ol>
            </div>

            {/* Env vars from backend */}
            {Object.keys(envVars).length > 0 && (
              <div className="card-glass p-5 space-y-3">
                <div className="flex items-center gap-2 mb-1">
                  <Key className="w-4 h-4 text-primary" />
                  <h4 className="text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground">Environment Variables</h4>
                </div>
                {Object.entries(envVars).map(([key, info]) => (
                  <div key={key} className="flex items-center gap-3 p-3 rounded-lg bg-background/50 border border-border/30">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-xs font-mono font-bold text-foreground">{key}</code>
                        {info.required && (
                          <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/20">Required</span>
                        )}
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-0.5">{info.description}</p>
                      {info.value && (
                        <code className="text-[11px] font-mono text-primary/70 mt-1 block">{info.value}</code>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => copyToClipboard(info.value || key, key)}
                      className="shrink-0 text-muted-foreground hover:text-foreground h-8 px-2"
                    >
                      {copied === key ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    </Button>
                  </div>
                ))}
              </div>
            )}

            {/* Query example */}
            <div className="card-glass p-5 space-y-3">
              <div className="flex items-center gap-2 mb-1">
                <Terminal className="w-4 h-4 text-primary" />
                <h4 className="text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground">Test with query_mcp.py</h4>
              </div>
              <div className="code-block p-4 text-xs font-mono text-foreground/80 space-y-1">
                <p><span className="text-primary font-bold">$</span> python query_mcp.py --server {dedalusUser}/{deployInfo.server_name} &quot;What can this server do?&quot;</p>
                <p className="text-muted-foreground mt-2"># Or interactive mode:</p>
                <p><span className="text-primary font-bold">$</span> python query_mcp.py --server {dedalusUser}/{deployInfo.server_name} --interactive</p>
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between pt-4">
          <Button variant="ghost" onClick={() => router.push("/adapter/test")} className="text-muted-foreground">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
          {deployInfo && (
            <Button onClick={() => router.push("/")} variant="outline" className="rounded-full px-6">
              <span>Back to Dashboard</span>
            </Button>
          )}
        </div>
      </div>
    </>
  );
}

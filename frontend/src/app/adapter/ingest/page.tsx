"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { StepHeader } from "@/components/adapter/StepHeader";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { usePipeline } from "@/lib/pipeline-context";
import { FileJson, Globe, Package, Upload, ArrowRight, Loader2, AlertCircle, FileUp, X } from "lucide-react";

const INPUT_SOURCES = [
  { key: "openapi", label: "OpenAPI / Swagger", sub: "URL or upload file", icon: FileJson },
  { key: "docs", label: "API Docs URL", sub: "Scrape & extract (Gemini)", icon: Globe },
  { key: "sdk", label: "SDK / Client Lib", sub: "GitHub repository URL", icon: Package },
  { key: "postman", label: "Postman Collection", sub: "Upload JSON file", icon: Upload },
];

const SOURCE_CONFIG: Record<string, { label: string; placeholder: string; hint: string; allowUpload: boolean }> = {
  openapi: {
    label: "Paste spec URL or Swagger UI URL",
    placeholder: "https://petstore.swagger.io/  or  http://127.0.0.1:8001/openapi.json",
    hint: "Supports OpenAPI 3.x, Swagger 2.x, YAML/JSON URLs",
    allowUpload: true,
  },
  docs: {
    label: "Paste API documentation URL",
    placeholder: "https://docs.example.com/api",
    hint: "Uses Gemini AI to extract endpoints from non-standard docs",
    allowUpload: true,
  },
  sdk: {
    label: "Paste GitHub repository URL",
    placeholder: "https://github.com/stripe/stripe-python",
    hint: "Supports Python, TypeScript, JavaScript, Java SDKs",
    allowUpload: false,
  },
  postman: {
    label: "Upload Postman Collection file",
    placeholder: "",
    hint: "Supports Postman Collection v2.1 JSON format",
    allowUpload: true,
  },
};

export default function IngestPage() {
  const router = useRouter();
  const { runIngest, runIngestFile, loading, error } = usePipeline();
  const [selected, setSelected] = useState("openapi");
  const [specUrl, setSpecUrl] = useState("");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const config = SOURCE_CONFIG[selected];

  const handleFileSelect = (file: File) => {
    const ext = file.name.toLowerCase();
    if (!ext.endsWith(".yaml") && !ext.endsWith(".yml") && !ext.endsWith(".json")) {
      return;
    }
    setUploadedFile(file);
    setSpecUrl("");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  };

  const handleParse = async () => {
    if (uploadedFile) {
      await runIngestFile(uploadedFile, selected);
    } else if (specUrl.trim()) {
      await runIngest(specUrl.trim(), selected);
    } else {
      return;
    }
    router.push("/adapter/discover");
  };

  const canSubmit = !!(uploadedFile || specUrl.trim());

  return (
    <>
      <StepHeader
        currentStep="ingest"
        title="Create New Adapter"
        description="Generate an MCP server from any software interface"
      />

      <div className="space-y-8">
        <div>
          <h3 className="text-sm font-semibold text-foreground mb-4">Select Input Source</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {INPUT_SOURCES.map((src) => {
              const Icon = src.icon;
              const isSelected = selected === src.key;
              return (
                <button
                  key={src.key}
                  onClick={() => { setSelected(src.key); setUploadedFile(null); setSpecUrl(""); }}
                  className={cn(
                    "card-glass p-4 text-left transition-all cursor-pointer group",
                    isSelected
                      ? "border-primary/50 bg-primary/5 glow-border"
                      : "hover:border-primary/20"
                  )}
                >
                  <Icon className={cn(
                    "w-5 h-5 mb-3 transition-colors",
                    isSelected ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                  )} />
                  <p className={cn(
                    "text-sm font-semibold mb-0.5 transition-colors",
                    isSelected ? "text-primary" : "text-foreground"
                  )}>{src.label}</p>
                  <p className="text-[11px] text-muted-foreground">{src.sub}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* URL input — shown for non-upload-only sources */}
        {config.placeholder && (
          <div>
            <label className="text-sm font-semibold text-foreground mb-3 block">
              {config.label}
            </label>
            <textarea
              value={specUrl}
              onChange={(e) => { setSpecUrl(e.target.value); setUploadedFile(null); }}
              placeholder={config.placeholder}
              className="w-full h-28 rounded-xl bg-card border border-border px-4 py-3 text-sm font-mono text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40 resize-none"
            />
          </div>
        )}

        {/* File upload area */}
        {config.allowUpload && (
          <div>
            {config.placeholder && (
              <div className="flex items-center gap-3 mb-3">
                <div className="h-px flex-1 bg-border/50" />
                <span className="text-xs text-muted-foreground font-medium">OR upload a file</span>
                <div className="h-px flex-1 bg-border/50" />
              </div>
            )}
            {!config.placeholder && (
              <label className="text-sm font-semibold text-foreground mb-3 block">
                {config.label}
              </label>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept=".yaml,.yml,.json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileSelect(file);
              }}
            />

            {uploadedFile ? (
              <div className="flex items-center gap-3 p-4 rounded-xl bg-primary/5 border border-primary/30">
                <FileUp className="w-5 h-5 text-primary shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-mono font-bold text-foreground truncate">{uploadedFile.name}</p>
                  <p className="text-[11px] text-muted-foreground">{(uploadedFile.size / 1024).toFixed(1)} KB</p>
                </div>
                <button
                  onClick={() => { setUploadedFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                  className="p-1 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  "flex flex-col items-center justify-center gap-2 p-8 rounded-xl border-2 border-dashed cursor-pointer transition-colors",
                  dragOver
                    ? "border-primary/50 bg-primary/5"
                    : "border-border/50 hover:border-primary/30 hover:bg-primary/5"
                )}
              >
                <FileUp className="w-6 h-6 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Drop a <strong>.yaml</strong>, <strong>.yml</strong>, or <strong>.json</strong> file here, or click to browse
                </p>
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        <div className="flex items-center justify-between pt-2">
          <p className="text-xs text-muted-foreground">
            {config.hint}
          </p>
          <Button
            onClick={handleParse}
            disabled={!canSubmit || loading}
            className="btn-gradient rounded-full px-6 relative z-10"
          >
            {loading ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Parsing...</>
            ) : (
              <><span>Parse & Continue</span> <ArrowRight className="w-4 h-4" /></>
            )}
          </Button>
        </div>
      </div>
    </>
  );
}

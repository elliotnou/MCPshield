"use client";

import { ArrowRight, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { FileJson, Search, Layers, Shield, Code2, TestTube, Rocket } from "lucide-react";

const STEPS = [
  { key: "ingest", label: "Ingest", icon: FileJson },
  { key: "discover", label: "Discover", icon: Search },
  { key: "schema", label: "Schema", icon: Layers },
  { key: "policy", label: "Policy", icon: Shield },
  { key: "generate", label: "Generate", icon: Code2 },
  { key: "test", label: "Test", icon: TestTube },
  { key: "deploy", label: "Deploy", icon: Rocket },
];

interface StepHeaderProps {
  currentStep: string;
  title: string;
  description: string;
}

export function StepHeader({ currentStep, title, description }: StepHeaderProps) {
  const currentIdx = STEPS.findIndex((s) => s.key === currentStep);

  return (
    <div className="mb-8">
      <div className="flex items-center gap-1.5 mb-6 overflow-x-auto pb-2">
        {STEPS.map((step, idx) => {
          const Icon = step.icon;
          const isActive = idx === currentIdx;
          const isDone = idx < currentIdx;
          return (
            <div key={step.key} className="flex items-center gap-1.5 shrink-0">
              <div
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary border border-primary/30 glow-border"
                    : isDone
                    ? "bg-secondary text-foreground border border-border"
                    : "bg-muted/50 text-muted-foreground border border-transparent"
                )}
              >
                <div className={cn(
                  "w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold",
                  isActive ? "bg-primary text-primary-foreground" : isDone ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
                )}>
                  {isDone ? <Check className="w-3 h-3" /> : idx + 1}
                </div>
                <span className="hidden sm:inline">{step.label}</span>
              </div>
              {idx < STEPS.length - 1 && (
                <ArrowRight className={cn("w-3 h-3 shrink-0", isDone ? "text-primary" : "text-muted-foreground/30")} />
              )}
            </div>
          );
        })}
      </div>
      <h1 className="text-2xl md:text-3xl font-extrabold text-foreground mb-2">{title}</h1>
      <p className="text-muted-foreground text-sm">{description}</p>
    </div>
  );
}

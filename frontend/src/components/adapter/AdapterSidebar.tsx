"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { NexusLogo } from "@/components/landing/NexusLogo";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import {
  FileJson, Search, Layers, Shield, Code2, TestTube, Rocket,
  LayoutDashboard, FileText, Coins,
} from "lucide-react";
import { useCredits } from "@/lib/use-credits";

const STEPS = [
  { key: "ingest", label: "Ingest", sub: "Parse & index", icon: FileJson, href: "/adapter/ingest", num: 1 },
  { key: "discover", label: "Discover", sub: "Mine capabilities", icon: Search, href: "/adapter/discover", num: 2 },
  { key: "schema", label: "Schema", sub: "Synthesize types", icon: Layers, href: "/adapter/schema", num: 3 },
  { key: "policy", label: "Policy", sub: "Safety rules", icon: Shield, href: "/adapter/policy", num: 4 },
  { key: "generate", label: "Generate", sub: "MCP server", icon: Code2, href: "/adapter/generate", num: 5 },
  { key: "test", label: "Test", sub: "Contract tests", icon: TestTube, href: "/adapter/test", num: 6 },
  { key: "deploy", label: "Deploy", sub: "Ship to production", icon: Rocket, href: "/adapter/deploy", num: 7 },
];

function CreditsBadge() {
  const { balance } = useCredits();

  return (
    <div className="flex items-center gap-2 p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/15">
      <Coins className="w-4 h-4 text-amber-400" />
      <div>
        <p className="text-xs font-bold text-foreground leading-tight">{balance}</p>
        <p className="text-[9px] text-muted-foreground">credits</p>
      </div>
    </div>
  );
}

export function AdapterSidebar() {
  const pathname = usePathname();
  const currentKey = STEPS.find((s) => pathname.startsWith(s.href))?.key ?? "ingest";
  const currentIdx = STEPS.findIndex((s) => s.key === currentKey);

  return (
    <aside className="w-[220px] shrink-0 h-screen sticky top-0 flex flex-col border-r border-border/40 bg-card/60 backdrop-blur-xl">
      <div className="px-5 py-5 flex items-center gap-2.5 border-b border-border/30">
        <NexusLogo size={28} animated />
        <span className="font-bold text-foreground text-sm tracking-tight">Anvil</span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        <Link
          href="/"
          className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-colors mb-3"
        >
          <LayoutDashboard className="w-4 h-4" />
          Dashboard
        </Link>

        <div className="px-3 mb-2">
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">Pipeline</p>
        </div>

        {STEPS.map((step, idx) => {
          const Icon = step.icon;
          const isActive = step.key === currentKey;
          const isDone = idx < currentIdx;

          return (
            <Link
              key={step.key}
              href={step.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all group relative",
                isActive
                  ? "bg-primary/10 text-primary border border-primary/20"
                  : isDone
                  ? "text-foreground hover:bg-secondary/50"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/30"
              )}
            >
              <div
                className={cn(
                  "w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold shrink-0 transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : isDone
                    ? "bg-primary/20 text-primary"
                    : "bg-muted text-muted-foreground"
                )}
              >
                {isDone ? "✓" : step.num}
              </div>
              <div className="min-w-0">
                <p className="font-medium truncate leading-tight">{step.label}</p>
                <p className="text-[10px] text-muted-foreground truncate">{step.sub}</p>
              </div>
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-4 border-t border-border/30 space-y-3">
        <CreditsBadge />
        <div className="flex items-center justify-between">
          <Link href="#" className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <FileText className="w-3.5 h-3.5" />
            Docs
          </Link>
          <ThemeSwitcher />
        </div>
        <div className="flex items-center gap-2.5 pt-2">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center text-xs font-bold text-primary-foreground shrink-0">
            A
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-foreground truncate">Anvil User</p>
            <p className="text-[10px] text-muted-foreground truncate">Local</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

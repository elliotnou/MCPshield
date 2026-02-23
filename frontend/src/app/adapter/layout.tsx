import { AdapterSidebar } from "@/components/adapter/AdapterSidebar";
import { PipelineProvider } from "@/lib/pipeline-context";

export default function AdapterLayout({ children }: { children: React.ReactNode }) {
  return (
    <PipelineProvider>
      <div className="flex min-h-screen bg-background">
        <AdapterSidebar />
        <main className="flex-1 min-w-0 overflow-y-auto">
          <div className="max-w-5xl mx-auto px-8 py-8">
            {children}
          </div>
        </main>
      </div>
    </PipelineProvider>
  );
}

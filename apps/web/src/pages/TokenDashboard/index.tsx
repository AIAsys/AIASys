import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TokenUsagePanel } from "@/components/settings/token-usage/TokenUsagePanel";

export default function TokenDashboard() {
  const handleBack = () => {
    globalThis.history.back();
  };

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="border-b border-border flex-shrink-0">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={handleBack}
              className="h-8 w-8"
            >
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <h1 className="text-base font-semibold">Token 消耗面板</h1>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <TokenUsagePanel embedded />
        </div>
      </main>
    </div>
  );
}

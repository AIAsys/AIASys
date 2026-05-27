import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { scenarioCards } from "./data";
import { sectionTitle } from "./shared";

export function ScenariosSection() {
  return (
    <section
      id="scenarios"
      className="scroll-mt-28 relative overflow-hidden bg-foreground px-4 py-24 sm:px-6 lg:px-8"
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.08),transparent_26%),radial-gradient(circle_at_78%_16%,rgba(56,189,248,0.18),transparent_26%),linear-gradient(180deg,rgba(2,6,23,1)_0%,rgba(3,7,18,0.98)_100%)]" />
      <div className="absolute inset-0 opacity-30 [background-image:linear-gradient(to_right,rgba(255,255,255,0.08)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.08)_1px,transparent_1px)] [background-size:96px_96px]" />

      <div className="relative mx-auto max-w-7xl">
        {sectionTitle(
          "典型场景",
          "适合真实任务，不适合只看热闹的演示",
          "当你的工作需要多轮推进、不断补充资料、保留中间结果并最终交付，这些场景会比一次性问答更接近你的日常。",
          "center",
          "dark",
        )}

        <div className="mt-14 grid gap-6 lg:grid-cols-[1.15fr_0.92fr_0.92fr]">
          {scenarioCards.map((card, index) => {
            const Icon = card.icon;

            return (
              <Card
                key={card.title}
                className={cn(
                  "relative overflow-hidden rounded-[2rem] border border-white/10 bg-white/6 text-white shadow-[0_44px_90px_-58px_rgba(0,0,0,0.72)] backdrop-blur-xl",
                  index === 0 ? "lg:min-h-[28rem]" : "",
                )}
              >
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/60 to-transparent" />
                <CardContent className="relative flex h-full flex-col p-6">
                  <div className="flex h-12 w-12 items-center justify-center rounded-[1.2rem] border border-white/12 bg-white/8 text-white">
                    <Icon className="h-5 w-5" />
                  </div>

                  <h3 className="mt-6 text-2xl font-semibold tracking-[-0.03em] text-white">
                    {card.title}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground sm:text-base">
                    {card.summary}
                  </p>

                  <div className="mt-8 space-y-3">
                    {card.steps.map((step) => (
                      <div
                        key={step}
                        className="flex items-start gap-3 rounded-[1.2rem] border border-white/10 bg-white/6 px-4 py-3 text-sm leading-6 text-muted-foreground"
                      >
                        <div className="mt-2 h-2 w-2 rounded-full bg-info" />
                        <div>{step}</div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-auto pt-6 text-sm leading-6 text-muted-foreground">
                    {card.outcome}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </section>
  );
}

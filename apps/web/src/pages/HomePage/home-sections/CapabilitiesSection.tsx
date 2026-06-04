import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { capabilityCards } from "./data";
import { sectionTitle, statusBadge } from "./shared";

export function CapabilitiesSection() {
  return (
    <section
      id="capabilities"
      className="scroll-mt-28 px-4 py-24 sm:px-6 lg:px-8"
    >
      <div className="mx-auto max-w-7xl">
        <div className="grid gap-8 lg:grid-cols-[minmax(0,0.84fr)_minmax(0,1.16fr)] lg:items-end">
          {sectionTitle(
            "能力总览",
            "一套系统串起分析、执行与结果沉淀",
            "Sub Agent 自动分解复杂任务，执行流实时可视化。如果你的工作不只是问一个问题，而是要处理资料、调用工具、保留过程并继续推进，这一页会更接近你的真实使用方式。",
          )}

          <div className="rounded-[2rem] border border-foreground/8 bg-white/74 p-6 shadow-[0_34px_70px_-52px_rgba(15,23,42,0.35)] backdrop-blur-sm sm:p-7">
            <div className="text-[11px] font-mono tracking-[0.2em] text-muted-foreground">
              适合的工作方式
            </div>
            <p className="mt-4 text-xl font-medium leading-9 tracking-[-0.03em] text-foreground sm:text-2xl">
              你看到的不是分散的功能入口，而是一条从理解任务、执行分析到沉淀结果的连续路径。
            </p>
            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              {[
                "围绕任务持续推进",
                "保留文件和中间结果",
                "进入真实可达入口",
              ].map((item) => (
                <div
                  key={item}
                  className="rounded-[1.4rem] border border-foreground/8 bg-muted/80 px-4 py-3 text-sm leading-6 text-muted-foreground"
                >
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-14 grid gap-6 lg:grid-cols-6">
          {capabilityCards.map((card, index) => {
            const Icon = card.icon;
            const columnClass =
              index < 2
                ? "lg:col-span-3"
                : index === 4
                  ? "lg:col-span-6 xl:col-span-2"
                  : "lg:col-span-3 xl:col-span-2";

            return (
              <Card
                key={card.title}
                className={cn(
                  "group relative overflow-hidden rounded-[2rem] border border-foreground/8 bg-white/76 shadow-[0_38px_80px_-60px_rgba(15,23,42,0.42)] backdrop-blur-sm transition-transform duration-300 hover:-translate-y-1.5",
                  columnClass,
                )}
              >
                <div
                  className={cn(
                    "absolute -right-16 -top-16 h-40 w-40 rounded-full blur-3xl",
                    card.glow,
                  )}
                />
                <div className={cn("absolute inset-x-0 top-0 h-1 bg-gradient-to-r", card.accent)} />
                <CardContent className="relative p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-[1.2rem] border border-foreground/8 bg-foreground text-white">
                      <Icon className="h-5 w-5" />
                    </div>
                    <Badge
                      variant="outline"
                      className="rounded-full border-foreground/8 bg-white/80 px-3 py-1 text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground"
                    >
                      核心能力
                    </Badge>
                  </div>

                  <h3 className="mt-6 text-2xl font-semibold tracking-[-0.03em] text-foreground">
                    {card.title}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground sm:text-base">
                    {card.summary}
                  </p>

                  <div className="mt-6 space-y-3">
                    {card.features.map((feature) => (
                      <div
                        key={feature.label}
                        className="flex items-start justify-between gap-3 rounded-[1.35rem] border border-foreground/8 bg-white/70 px-4 py-3"
                      >
                        <div className="text-sm leading-6 text-muted-foreground">
                          {feature.label}
                        </div>
                        {statusBadge(feature.status, feature.tone)}
                      </div>
                    ))}
                  </div>

                  <p className="mt-5 text-sm leading-6 text-muted-foreground">{card.note}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </section>
  );
}

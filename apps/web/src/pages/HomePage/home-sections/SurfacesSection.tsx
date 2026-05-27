import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { renderSurfacePreview, sectionTitle } from "./shared";
import { surfacePreviewCards } from "./data";

interface SurfacesSectionProps {
  isAuthenticated: boolean;
}

export function SurfacesSection({ isAuthenticated }: SurfacesSectionProps) {
  return (
    <section
      id="surfaces"
      className="scroll-mt-28 relative overflow-hidden px-4 py-24 sm:px-6 lg:px-8"
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(15,23,42,0.08),transparent_28%),linear-gradient(180deg,#fffdf8_0%,#ffffff_54%,#f8fafc_100%)]" />
      <div className="absolute inset-0 opacity-20 [background-image:linear-gradient(to_right,rgba(15,23,42,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(15,23,42,0.05)_1px,transparent_1px)] [background-size:88px_88px]" />

      <div className="relative mx-auto max-w-7xl">
        <div className="grid gap-8 lg:grid-cols-[minmax(0,0.86fr)_minmax(0,1.14fr)] lg:items-end">
          {sectionTitle(
            "核心工作区",
            "进到系统后，你可以从这些入口开始",
            "首页更应该先告诉你这套产品能帮你做什么。下面这几块分别对应分析任务、资料整理和知识探索，方便你判断从哪里开始最合适。",
          )}

          <div className="rounded-[2rem] border border-foreground/8 bg-white/78 p-6 shadow-[0_34px_72px_-54px_rgba(15,23,42,0.34)] backdrop-blur-sm sm:p-7">
            <div className="text-[11px] font-mono tracking-[0.2em] text-muted-foreground">
              先帮你判断
            </div>
            <p className="mt-4 text-xl font-medium leading-9 tracking-[-0.03em] text-foreground sm:text-2xl">
              先看清每个入口适合处理什么事，再决定从哪里开始，会比先记一堆功能名更直观。
            </p>
            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              {[
                "分析任务有独立工作台，可以持续推进",
                "资料可以整理进知识库，便于后续检索",
                "需要关系视角时，再进入图谱继续探索",
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

        <div className="mt-14 grid gap-5 sm:gap-6 grid-cols-1 md:grid-cols-2">
          {surfacePreviewCards.map((card) => (
            <Card
              key={card.title}
              className="overflow-hidden rounded-[1.5rem] sm:rounded-[2rem] border border-foreground/8 bg-white/80 shadow-[0_40px_84px_-60px_rgba(15,23,42,0.38)] backdrop-blur-sm"
            >
              <CardContent className="p-4 sm:p-6">
                <div className="flex items-center justify-between">
                  <Badge
                    variant="outline"
                    className="rounded-full border-foreground/8 bg-foreground px-2.5 py-0.5 sm:px-3 sm:py-1 text-[10px] sm:text-[11px] font-mono uppercase tracking-[0.18em] text-white"
                  >
                    主要入口
                  </Badge>
                </div>

                <h3 className="mt-4 sm:mt-5 text-xl sm:text-2xl font-semibold tracking-[-0.03em] text-foreground">
                  {card.title}
                </h3>
                <p className="mt-2 sm:mt-3 text-sm leading-6 sm:leading-7 text-muted-foreground">
                  {card.summary}
                </p>

                <div className="mt-4 sm:mt-5 rounded-[1.2rem] sm:rounded-[1.6rem] border border-foreground/8 bg-[linear-gradient(180deg,#ffffff_0%,#f8fafc_100%)] p-2.5 sm:p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
                  {renderSurfacePreview(card.kind)}
                </div>

                <div className="mt-4 sm:mt-5 space-y-2">
                  {card.bullets.map((bullet) => (
                    <div
                      key={bullet}
                      className="rounded-[1rem] sm:rounded-[1.2rem] border border-foreground/8 bg-muted/80 px-3 py-2 sm:px-4 sm:py-2.5 text-xs sm:text-sm leading-5 sm:leading-6 text-muted-foreground"
                    >
                      {bullet}
                    </div>
                  ))}
                </div>

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-4 sm:mt-5 w-full rounded-full border-foreground/12 bg-white/80 text-foreground hover:bg-muted"
                  onClick={() => card.onClick(isAuthenticated)}
                >
                  {card.actionLabel}
                  <ArrowRight className="h-3.5 w-3.5 sm:h-4 sm:w-4 ml-1" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}

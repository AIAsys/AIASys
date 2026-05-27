import { ArrowRight, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { scrollToHomeSection } from "../navigation";
import { entryCards } from "./data";

interface TrustSectionProps {
  isAuthenticated: boolean;
}

export function TrustSection({ isAuthenticated }: TrustSectionProps) {
  return (
    <section
      id="trust"
      className="scroll-mt-28 border-t border-foreground/8 bg-[linear-gradient(180deg,rgba(247,247,243,0.9)_0%,rgba(255,255,255,0.82)_100%)] px-4 py-24 sm:px-6 lg:px-8"
    >
      <div className="mx-auto max-w-7xl">
        <div className="mt-16 sm:mt-20 flex flex-col items-center text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-foreground/8 bg-white/78 px-3 py-1 text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
            后续规划
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            技能社区市场 · 多模态能力 · 企业级审计
          </p>
        </div>

        <div className="mt-10 overflow-hidden rounded-[2rem] sm:rounded-[2.4rem] border border-foreground/8 bg-white/82 p-5 sm:p-8 shadow-[0_40px_90px_-62px_rgba(15,23,42,0.42)] backdrop-blur-xl">
          <div className="grid gap-8 lg:grid-cols-[minmax(0,0.92fr)_minmax(320px,1.08fr)] lg:items-end">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-foreground/8 bg-white/78 px-3 py-1 text-[11px] font-mono uppercase tracking-[0.24em] text-muted-foreground">
                <ShieldCheck className="h-3.5 w-3.5" />
                开始体验
              </div>
              <h3 className="mt-5 text-3xl font-semibold tracking-[-0.04em] text-foreground sm:text-[2.4rem]">
                先继续了解产品，或者直接进入真实入口
              </h3>
              <p className="mt-4 text-sm leading-7 text-muted-foreground sm:text-base">
                如果你想先判断艾斯是否适合你的任务，可以继续浏览首页分区。
                如果你已经准备试用，下列入口都是真实页面，可以直接进入当前工作区主链路。
              </p>

              <Button
                type="button"
                size="lg"
                className="mt-7 min-w-[190px] rounded-full bg-foreground px-7 text-white shadow-[0_24px_50px_-34px_rgba(15,23,42,0.82)] hover:bg-muted"
                onClick={() => entryCards[0].onClick(isAuthenticated)}
              >
                进入分析主链路
              </Button>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              {entryCards.map((card) => (
                <Card
                  key={card.title}
                  className="rounded-[1.8rem] border border-foreground/8 bg-muted/65 shadow-[0_26px_52px_-40px_rgba(15,23,42,0.28)]"
                >
                  <CardContent className="flex h-full flex-col justify-between gap-5 p-5">
                    <div>
                      <h4 className="text-lg font-semibold tracking-[-0.02em] text-foreground">
                        {card.title}
                      </h4>
                      <p className="mt-3 text-sm leading-6 text-muted-foreground">
                        {card.description}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      className="justify-between rounded-full border-foreground/10 bg-white/80 text-muted-foreground"
                      onClick={() => card.onClick(isAuthenticated)}
                    >
                      {card.action}
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          <div className="mt-8 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            {[
              "真实入口可直接到达",
              "能力状态说明清楚",
              "支持继续复盘与交接",
            ].map((label) => (
              <Badge
                key={label}
                variant="outline"
                className="rounded-full border-foreground/8 bg-white/76 px-3 py-1"
              >
                {label}
              </Badge>
            ))}
          </div>
        </div>

        <div className="mt-8 flex justify-center">
          <Button
            type="button"
            variant="ghost"
            className="rounded-full text-muted-foreground"
            onClick={() => scrollToHomeSection("capabilities")}
          >
            回到能力总览
          </Button>
        </div>
      </div>
    </section>
  );
}

import { Button } from "@/components/ui/button";
import { BrandLogo } from "@/components/branding/BrandLogo";
import {
  ArrowRight,
  Bot,
  FolderKanban,
  ShieldCheck,
} from "lucide-react";
import { Pill } from "./Pill";
import { goToAnalysis, scrollToHomeSection } from "./navigation";

const narrativeSignals = [
  {
    title: "拆得开",
    description: "复杂任务自动分解为可并行的子任务，多 Agent 同时推进，实时可见每一步。",
  },
  {
    title: "接得上",
    description: "分析不是一次性问答。随时回到上下文继续推进，不丢失任何中间思考。",
  },
  {
    title: "留得住",
    description: "对话、代码、图表、结论——全部沉淀在工作区，复盘和交接都有迹可循。",
  },
] as const;

const systemPreview = [
  {
    icon: Bot,
    title: "多 Agent 并行",
    description: "Host 智能拆解任务，多个 Sub Agent 同时执行，大幅缩短等待时间。",
  },
  {
    icon: ShieldCheck,
    title: "本地执行",
    description: "开箱即用，代码和查询都在本地运行，数据不出你的机器。",
  },
  {
    icon: FolderKanban,
    title: "过程可视化",
    description: "右侧边栏实时呈现执行流和工具调用，每一步都看得见。",
  },
] as const;

const compactPanels = [
  {
    title: "多 Agent 并行",
    detail: "任务智能分解，多个 Sub Agent 同时推进，效率成倍提升。",
  },
  {
    title: "本地执行",
    detail: "打开即用，对话、代码、结果全部留在你的工作区里。",
  },
] as const;

const surfaceTags = [
  "多 Agent",
  "代码执行",
  "知识库",
  "技能",
  "本地执行",
  "执行流",
] as const;

export const Hero = () => {
  return (
    <section className="relative isolate overflow-hidden border-b border-foreground/8">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(15,23,42,0.1),transparent_30%),radial-gradient(circle_at_78%_20%,rgba(59,130,246,0.15),transparent_28%),linear-gradient(180deg,#ffffff_0%,#f8fafc_56%,#ffffff_100%)]" />
      <div className="absolute inset-0 opacity-40 [background-image:linear-gradient(to_right,rgba(15,23,42,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(15,23,42,0.05)_1px,transparent_1px)] [background-size:88px_88px]" />
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-white via-white/80 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-4 pb-12 sm:pb-16 lg:pb-20 pt-20 sm:pt-24 lg:pt-28 sm:px-6 lg:px-8">
        <div className="grid items-start gap-8 lg:gap-12 lg:grid-cols-2">
          <div>
            <Pill>AI 驱动的分析与知识工作台</Pill>

            <h1 className="mt-6 sm:mt-8 text-4xl sm:text-5xl lg:text-[4rem] xl:text-[4.5rem] font-semibold leading-[1.1] sm:leading-[0.95] tracking-[-0.03em] sm:tracking-[-0.05em] text-foreground">
              让复杂分析
              <span className="mt-1 sm:mt-2 block font-light text-muted-foreground">
                有章可循
              </span>
            </h1>

            <p className="mt-5 sm:mt-8 max-w-lg text-sm sm:text-base leading-7 sm:leading-8 text-muted-foreground">
              数据分析、代码执行、知识检索、Agent 协作——在同一界面中无缝流转，每一步都可追溯。
            </p>

            <div className="mt-8 flex flex-wrap gap-2 sm:gap-3">
              {surfaceTags.slice(0, 6).map((tag) => (
                <div
                  key={tag}
                  className="rounded-full border border-foreground/10 bg-white/72 px-3 py-1.5 text-[11px] sm:text-[12px] font-medium tracking-[0.04em] text-muted-foreground shadow-[0_16px_28px_-24px_rgba(15,23,42,0.32)] backdrop-blur-sm whitespace-nowrap"
                >
                  {tag}
                </div>
              ))}
            </div>

            <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4">
              <Button
                type="button"
                size="lg"
                className="w-full sm:w-auto sm:min-w-[160px] rounded-full bg-foreground px-6 text-white shadow-[0_22px_45px_-30px_rgba(15,23,42,0.8)] hover:bg-foreground"
                onClick={() => goToAnalysis()}
              >
                开始分析
                <ArrowRight className="h-4 w-4 ml-1" />
              </Button>

              <Button
                type="button"
                variant="outline"
                size="lg"
                className="w-full sm:w-auto sm:min-w-[160px] rounded-full border-foreground/12 bg-white/72 px-6 text-muted-foreground shadow-[0_18px_36px_-28px_rgba(15,23,42,0.4)] backdrop-blur-sm hover:bg-white"
                onClick={() => scrollToHomeSection("capabilities")}
              >
                了解更多
              </Button>
            </div>
          </div>

          <div className="relative lg:pl-4">
            <div className="absolute inset-4 sm:inset-8 rounded-[2rem] sm:rounded-[2.6rem] bg-foreground/10 blur-3xl" />
            <div className="relative overflow-hidden rounded-[1.5rem] sm:rounded-[2.25rem] border border-foreground/10 bg-white/72 p-3 sm:p-4 shadow-[0_48px_110px_-62px_rgba(15,23,42,0.45)] backdrop-blur-2xl">
              <div className="rounded-[1.3rem] sm:rounded-[1.6rem] border border-white/90 bg-[linear-gradient(180deg,rgba(255,255,255,0.92)_0%,rgba(248,250,252,0.84)_100%)] p-3 sm:p-5">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <div className="text-[10px] sm:text-[11px] font-mono tracking-[0.2em] text-muted-foreground">
                      核心能力
                    </div>
                    <div className="mt-1 text-base sm:text-lg font-semibold tracking-[-0.03em] text-foreground">
                      自动分解，并行执行
                      <span className="block text-muted-foreground text-xs sm:text-sm font-normal">全流程可视化追踪</span>
                    </div>
                  </div>
                  <div className="flex-shrink-0">
                    <div className="inline-flex rounded-[1rem] sm:rounded-[1.3rem] border border-foreground/8 bg-white/82 px-2.5 py-2 sm:px-3 sm:py-2.5 shadow-[0_16px_30px_-24px_rgba(15,23,42,0.32)] backdrop-blur-sm">
                      <BrandLogo
                        variant="stacked"
                        alt="艾斯"
                        className="h-10 sm:h-12 w-auto object-contain"
                      />
                    </div>
                  </div>
                </div>

                <div className="mt-4 sm:mt-5 grid gap-3 grid-cols-1">
                  <div className="rounded-[1.3rem] sm:rounded-[1.5rem] border border-foreground/8 bg-foreground p-3 sm:p-4 text-primary-foreground shadow-[0_22px_50px_-34px_rgba(15,23,42,0.8)]">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/8">
                        <ShieldCheck className="h-4 w-4" />
                      </div>
                      <div className="text-sm sm:text-base font-semibold text-white">
                        全链路可观测
                      </div>
                    </div>

                    <div className="space-y-2">
                      {systemPreview.map((item, index) => {
                        const Icon = item.icon;
                        return (
                          <div
                            key={item.title}
                            className="rounded-[1rem] border border-white/10 bg-white/6 px-3 py-2"
                          >
                            <div className="flex items-center gap-2.5">
                              <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-lg bg-white/10 text-white">
                                <Icon className="h-3 w-3" />
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="text-[11px] sm:text-xs font-medium text-white truncate">
                                  {index + 1}. {item.title}
                                </div>
                                <p className="text-[10px] sm:text-[11px] leading-4 text-muted-foreground truncate">
                                  {item.description}
                                </p>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 sm:gap-3">
                    {compactPanels.map((panel) => (
                      <div
                        key={panel.title}
                        className="rounded-[1.2rem] sm:rounded-[1.35rem] border border-foreground/8 bg-white/78 p-2.5 sm:p-3 shadow-[0_22px_40px_-34px_rgba(15,23,42,0.35)]"
                      >
                        <div className="text-[11px] sm:text-xs font-semibold tracking-[-0.02em] text-foreground truncate">
                          {panel.title}
                        </div>
                        <p className="mt-1 text-[10px] sm:text-[11px] leading-4 text-muted-foreground line-clamp-2">
                          {panel.detail}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-8 sm:mt-12 grid gap-3 border-t border-foreground/8 pt-5 sm:pt-8 grid-cols-1 sm:grid-cols-3">
          {narrativeSignals.map((signal) => (
            <div
              key={signal.title}
              className="rounded-[1.3rem] border border-foreground/8 bg-white/62 p-3.5 sm:p-4 shadow-[0_26px_50px_-40px_rgba(15,23,42,0.32)] backdrop-blur-sm"
            >
              <div className="text-[10px] font-mono tracking-[0.2em] text-muted-foreground">
                产品理念
              </div>
              <div className="mt-2 text-sm sm:text-base font-semibold tracking-[-0.02em] text-foreground">
                {signal.title}
              </div>
              <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                {signal.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

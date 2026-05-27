import { ArrowRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { workflowSteps } from "./data";
import { sectionTitle } from "./shared";

export function WorkflowSection() {
  return (
    <section
      id="workflow"
      className="scroll-mt-28 px-4 py-24 sm:px-6 lg:px-8"
    >
      <div className="mx-auto max-w-7xl">
        {sectionTitle(
          "任务路径",
          "从输入资料到交付结果，每一步都能继续衔接",
          "复杂任务自动分解、并行执行，右侧边栏实时展示执行流。任务上下文、执行过程和结果沉淀被放进同一条连续路径里。",
          "center",
        )}

        <div className="mt-14 grid gap-5 lg:grid-cols-5">
          {workflowSteps.map((step, index) => {
            const Icon = step.icon;
            return (
              <div key={step.title} className="relative">
                <Card className="h-full rounded-[1.9rem] border border-foreground/8 bg-white/76 shadow-[0_34px_70px_-56px_rgba(15,23,42,0.35)] backdrop-blur-sm">
                  <CardContent className="flex h-full flex-col gap-5 p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex h-12 w-12 items-center justify-center rounded-[1.2rem] border border-foreground/8 bg-foreground text-white">
                        <Icon className="h-5 w-5" />
                      </div>
                      <span className="text-sm font-mono tracking-[0.16em] text-muted-foreground">
                        0{index + 1}
                      </span>
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold tracking-[-0.02em] text-foreground">
                        {step.title}
                      </h3>
                      <p className="mt-3 text-sm leading-7 text-muted-foreground">
                        {step.detail}
                      </p>
                    </div>
                  </CardContent>
                </Card>
                {index < workflowSteps.length - 1 ? (
                  <div className="absolute -right-3 top-1/2 z-10 hidden -translate-y-1/2 lg:block">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full border border-foreground/8 bg-white shadow-[0_16px_35px_-28px_rgba(15,23,42,0.32)]">
                      <ArrowRight className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

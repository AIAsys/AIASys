import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SectionTone, StatusTone, SurfacePreviewKind } from "./types";

export function sectionTitle(
  eyebrow: string,
  title: string,
  description: string,
  align: "left" | "center" = "left",
  tone: SectionTone = "light",
) {
  const dark = tone === "dark";

  return (
    <div
      className={cn(align === "center" ? "text-center" : "", dark ? "text-white" : "")}
    >
      <div
        className={cn(
          "inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-medium tracking-[0.12em]",
          dark
            ? "border border-white/12 bg-white/8 text-muted-foreground"
            : "border border-foreground/8 bg-white/72 text-muted-foreground shadow-[0_16px_35px_-28px_rgba(15,23,42,0.32)] backdrop-blur-sm",
        )}
      >
        <Sparkles className="h-3.5 w-3.5" />
        {eyebrow}
      </div>
      <h2
        className={cn(
          "mt-5 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl lg:text-[2.9rem]",
          dark ? "text-white" : "text-foreground",
        )}
      >
        {title}
      </h2>
      <p
        className={cn(
          "mt-4 max-w-3xl text-sm leading-7 sm:text-base",
          align === "center" ? "mx-auto" : "",
          dark ? "text-muted-foreground" : "text-muted-foreground",
        )}
      >
        {description}
      </p>
    </div>
  );
}

export function statusBadge(status: string, tone: StatusTone, dark = false) {
  const className = dark
    ? {
        ready: "border-transparent bg-white text-foreground",
        beta: "border-transparent bg-warning-container text-warning",
        planned: "border-white/12 bg-white/8 text-muted-foreground",
      }[tone]
    : {
        ready: "border-transparent bg-foreground text-white",
        beta: "border-transparent bg-warning-container text-warning",
        planned: "border-foreground/8 bg-white text-muted-foreground",
      }[tone];

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium tracking-wide",
        className,
      )}
    >
      {status}
    </span>
  );
}

export function renderSurfacePreview(kind: SurfacePreviewKind) {
  if (kind === "analysis") {
    return (
      <div className="grid h-full grid-cols-[72px_minmax(0,1fr)_96px] gap-2">
        <div className="rounded-[1.1rem] border border-foreground/8 bg-foreground/96 p-2">
          <div className="rounded-md bg-white/10 px-2 py-1 text-[10px] font-medium text-white">
            任务
          </div>
          <div className="mt-2 space-y-1.5">
            {["w-[44px]", "w-9", "w-[30px]"].map((widthClass, index) => (
              <div
                key={`analysis-nav-${index}`}
                className={cn("h-2 rounded-full bg-white/10", widthClass)}
              />
            ))}
          </div>
        </div>
        <div className="rounded-[1.1rem] border border-foreground/8 bg-white p-2.5">
          <div className="flex items-center gap-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-muted" />
            <div className="h-2.5 w-2.5 rounded-full bg-muted" />
            <div className="h-2.5 w-2.5 rounded-full bg-muted" />
          </div>
          <div className="mt-3 space-y-2">
            <div className="ml-auto w-[72%] rounded-2xl bg-foreground px-3 py-2 text-[10px] leading-4 text-white">
              帮我分析这批数据并保留过程。
            </div>
            <div className="w-[86%] rounded-2xl border border-foreground/8 bg-muted px-3 py-2 text-[10px] leading-4 text-muted-foreground">
              已进入任务上下文，开始执行并同步写入工作区。
            </div>
            <div className="w-[78%] rounded-2xl border border-dashed border-border bg-white px-3 py-2 text-[10px] leading-4 text-muted-foreground">
              [TOOL] Python / SQL / AskUser / 导出
            </div>
          </div>
          <div className="mt-3 h-8 rounded-[0.9rem] border border-foreground/8 bg-muted" />
        </div>
        <div className="rounded-[1.1rem] border border-foreground/8 bg-muted p-2.5">
          <div className="text-[10px] font-medium text-muted-foreground">工作区</div>
          <div className="mt-2 space-y-1.5">
            {["summary.md", "chart.png", "export.zip"].map((label) => (
              <div
                key={label}
                className="rounded-md border border-foreground/8 bg-white px-2 py-1 text-[10px] text-muted-foreground"
              >
                {label}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (kind === "knowledge") {
    return (
      <div className="grid h-full grid-cols-[118px_minmax(0,1fr)] gap-2">
        <div className="rounded-[1.1rem] border border-foreground/8 bg-white p-2.5">
          <div className="text-[10px] font-medium text-muted-foreground">知识库</div>
          <div className="mt-2 space-y-1.5">
            {["生产周报", "异常案例", "设备手册"].map((label, index) => (
              <div
                key={label}
                className={cn(
                  "rounded-md px-2 py-1 text-[10px]",
                  index === 0
                    ? "border border-foreground/8 bg-foreground text-white"
                    : "border border-foreground/8 bg-muted text-muted-foreground",
                )}
              >
                {label}
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-[1.1rem] border border-foreground/8 bg-muted p-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[10px] font-medium text-muted-foreground">文档与检索</div>
            <div className="rounded-full bg-white px-2 py-1 text-[9px] font-medium text-muted-foreground">
              Upload
            </div>
          </div>
          <div className="mt-2 rounded-[0.95rem] border border-foreground/8 bg-white px-3 py-2 text-[10px] text-muted-foreground">
            检索：最近一个月设备异常原因
          </div>
          <div className="mt-2 space-y-1.5">
            {[
              { top: "w-[58%]", bottom: "w-[40%]" },
              { top: "w-[88%]", bottom: "w-[70%]" },
              { top: "w-[74%]", bottom: "w-[56%]" },
            ].map((widthPair, index) => (
              <div
                key={`knowledge-result-${index}`}
                className="rounded-[0.9rem] border border-foreground/8 bg-white px-3 py-2"
              >
                <div className={cn("h-2 rounded-full bg-muted", widthPair.top)} />
                <div
                  className={cn("mt-1.5 h-2 rounded-full bg-muted", widthPair.bottom)}
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (kind === "skills") {
    return (
      <div className="grid h-full grid-cols-[minmax(0,1fr)_100px] gap-2">
        <div className="rounded-[1.1rem] border border-foreground/8 bg-muted p-2.5">
          <div className="text-[10px] font-medium text-muted-foreground">技能列表</div>
          <div className="mt-2 space-y-1.5">
            {["数据分析", "文档处理", "SQL 助手"].map((label, index) => (
              <div
                key={label}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px]",
                  index === 0
                    ? "border border-foreground/8 bg-foreground text-white"
                    : "border border-foreground/8 bg-white text-muted-foreground",
                )}
              >
                <div className={cn("h-2 w-2 rounded-full", index === 0 ? "bg-success" : "bg-muted")} />
                {label}
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-[1.1rem] border border-foreground/8 bg-white p-2.5">
          <div className="text-[10px] font-medium text-muted-foreground">已安装</div>
          <div className="mt-2 flex flex-col items-center justify-center gap-1">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-success-container text-success">
              <span className="text-[10px] font-bold">8</span>
            </div>
            <div className="text-[9px] text-muted-foreground">个技能</div>
          </div>
          <div className="mt-2 rounded-md bg-foreground px-2 py-1 text-[9px] text-center text-white">
            安装
          </div>
        </div>
      </div>
    );
  }

  // graph (knowledge graph) preview
  return (
    <div className="grid h-full grid-cols-[minmax(0,1fr)_118px] gap-2">
      <div className="rounded-[1.1rem] border border-foreground/8 bg-foreground p-2.5">
        <div className="flex h-full items-center justify-center rounded-[0.95rem] border border-white/10 bg-white/6">
          <div className="relative h-28 w-full">
            {[
              "left-[18%] top-[48%]",
              "left-[42%] top-[20%]",
              "left-[44%] top-[54%]",
              "left-[68%] top-[36%]",
              "left-[80%] top-[62%]",
            ].map((position, index) => (
              <div
                key={`graph-node-${index}`}
                className={cn(
                  "absolute h-4 w-4 rounded-full border border-white/20",
                  index === 2 ? "bg-warning" : "bg-info/80",
                  position,
                )}
              />
            ))}
            <div className="absolute left-[22%] top-[52%] h-px w-[22%] bg-white/20" />
            <div className="absolute left-[46%] top-[28%] h-[28%] w-px bg-white/20" />
            <div className="absolute left-[48%] top-[56%] h-px w-[24%] bg-white/20" />
            <div className="absolute left-[70%] top-[44%] h-[20%] w-px bg-white/20" />
          </div>
        </div>
      </div>
      <div className="rounded-[1.1rem] border border-foreground/8 bg-white p-2.5">
        <div className="text-[10px] font-medium text-muted-foreground">实体详情</div>
        <div className="mt-2 rounded-[0.95rem] border border-foreground/8 bg-muted px-3 py-2 text-[10px] text-muted-foreground">
          设备 A
        </div>
        <div className="mt-2 space-y-1.5">
          {["w-[72%]", "w-[54%]", "w-[64%]"].map((widthClass, index) => (
            <div
              key={`graph-detail-${index}`}
              className={cn("h-2 rounded-full bg-muted", widthClass)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

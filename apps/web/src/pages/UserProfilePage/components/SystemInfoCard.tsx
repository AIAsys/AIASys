/**
 * 系统信息卡片
 */

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Monitor, Server, ChevronDown, ChevronUp } from "lucide-react";
import { useVersionInfo } from "../hooks/useVersionInfo";

export function SystemInfoCard() {
  const {
    showVersionDetails,
    backendVersion,
    frontendVersion,
    systemVersion,
    toggleVersionDetails,
  } = useVersionInfo();

  return (
    <Card>
      <CardHeader>
        <CardTitle>系统信息</CardTitle>
        <CardDescription>查看当前系统版本</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* 主版本号 */}
          <div
            className="flex items-center justify-between py-3 px-4 bg-secondary rounded-lg cursor-pointer hover:bg-secondary/80 transition-colors"
            onClick={toggleVersionDetails}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                toggleVersionDetails();
              }
            }}
          >
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium">当前版本</span>
              <code className="px-2 py-0.5 bg-background rounded text-sm font-mono text-primary">
                {systemVersion}
              </code>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={(e) => {
                e.stopPropagation();
                toggleVersionDetails();
              }}
            >
              {showVersionDetails ? (
                <ChevronUp className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              )}
            </Button>
          </div>

          {/* 详细版本信息 */}
          {showVersionDetails && (
            <div className="space-y-2 pt-2 border-t border-border transition-all duration-200 ease-out">
              <div className="flex items-center justify-between py-2 px-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Monitor className="w-4 h-4" />
                  <span>客户端版本</span>
                </div>
                <code className="text-sm font-mono">{frontendVersion}</code>
              </div>
              <div className="flex items-center justify-between py-2 px-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Server className="w-4 h-4" />
                  <span>服务端版本</span>
                </div>
                <code className="text-sm font-mono">{backendVersion}</code>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

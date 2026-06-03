/**
 * LLM 配置卡片
 */

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Bot, Key } from "lucide-react";

interface LLMConfigCardProps {
  onNavigate?: (path: string) => void;
}

const MODEL_SETTINGS_PATH = "/workspace";

export function LLMConfigCard({ onNavigate }: LLMConfigCardProps) {
  const handleConfig = () => {
    const nav = (window as Window & { appNavigate?: (path: string) => void }).appNavigate;
    if (nav) {
      nav(MODEL_SETTINGS_PATH);
    } else if (onNavigate) {
      onNavigate(MODEL_SETTINGS_PATH);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI 模型配置</CardTitle>
        <CardDescription>管理您的 LLM 服务商和模型配置</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex items-center justify-between py-3 px-4 bg-muted/30 rounded-lg">
            <div className="flex items-center gap-3">
              <Bot className="w-5 h-5 text-tertiary" />
              <div>
                <p className="font-medium">自定义 LLM 配置</p>
                <p className="text-sm text-muted-foreground">
                  配置您自己的 API Key 或选择系统提供的模型
                </p>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={handleConfig}>
              <Key className="w-4 h-4 mr-2" />
              配置
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

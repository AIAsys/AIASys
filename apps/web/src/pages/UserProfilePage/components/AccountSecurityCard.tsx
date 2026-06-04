/**
 * 账户安全卡片
 */

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Shield } from "lucide-react";

interface AccountSecurityCardProps {
  isLocalEditable: boolean;
  onShowAuthModeNotice: () => void;
}

export function AccountSecurityCard({
  isLocalEditable,
  onShowAuthModeNotice,
}: AccountSecurityCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>账户安全</CardTitle>
        <CardDescription>管理您的账户安全设置</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex items-center justify-between py-3 px-4 bg-muted/30 rounded-lg">
            <div className="flex items-center gap-3">
              <Shield className="w-5 h-5 text-success" />
              <div>
                <p className="font-medium">身份模式</p>
                <p className="text-sm text-muted-foreground">
                  {isLocalEditable
                    ? "当前为单机默认用户模式，身份固定为本地工作区用户"
                    : "当前运行模式不支持在此页面修改认证来源"}
                </p>
              </div>
            </div>
            {isLocalEditable ? (
              <span className="text-sm font-medium text-success">本地默认用户</span>
            ) : (
              <Button variant="outline" size="sm" onClick={onShowAuthModeNotice}>
                查看说明
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

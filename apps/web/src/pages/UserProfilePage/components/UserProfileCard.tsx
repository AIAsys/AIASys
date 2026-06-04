/**
 * 用户资料卡片
 */

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Loader2, User, Mail, Phone, Calendar, Shield, ExternalLink, Edit2 } from "lucide-react";
import { formatCreatedAt, getAvatarColor, getDisplayChar } from "../utils";
import type { AuthUser } from "../types";

interface UserProfileCardProps {
  user: AuthUser | null;
  isEditing: boolean;
  isSaving: boolean;
  isLocalEditable: boolean;
  nameInput: string;
  phoneInput: string;
  onNameChange: (value: string) => void;
  onPhoneChange: (value: string) => void;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
  onShowAuthModeNotice: () => void;
}

export function UserProfileCard({
  user,
  isEditing,
  isSaving,
  isLocalEditable,
  nameInput,
  phoneInput,
  onNameChange,
  onPhoneChange,
  onStartEdit,
  onCancelEdit,
  onSave,
  onShowAuthModeNotice,
}: UserProfileCardProps) {
  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>基本信息</CardTitle>
            <CardDescription>查看您的个人资料信息</CardDescription>
          </div>
          {isLocalEditable ? (
            <div className="flex gap-2">
              {isEditing ? (
                <>
                  <Button variant="outline" onClick={onCancelEdit} disabled={isSaving}>
                    取消
                  </Button>
                  <Button onClick={onSave} disabled={isSaving}>
                    {isSaving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                    保存
                  </Button>
                </>
              ) : (
                <Button onClick={onStartEdit} className="gap-2">
                  <Edit2 className="w-4 h-4" />
                  编辑资料
                </Button>
              )}
            </div>
          ) : (
            <Button onClick={onShowAuthModeNotice} className="gap-2">
              <ExternalLink className="w-4 h-4" />
              查看模式说明
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* 头像和基本信息 */}
        <div className="flex items-center gap-6">
          <div
            className={`w-20 h-20 rounded-full ${getAvatarColor(user)} flex items-center justify-center shadow-lg`}
          >
            <span className="text-2xl font-semibold text-white">
              {getDisplayChar(user)}
            </span>
          </div>
          <div className="flex-1">
            <h3 className="text-xl font-semibold">
              {user?.nickname || "未设置昵称"}
            </h3>
            <div className="flex items-center gap-2 text-muted-foreground mt-1">
              <Mail className="w-4 h-4" />
              <span>{user?.email || "-"}</span>
            </div>
            <div className="flex items-center gap-2 text-muted-foreground mt-1">
              <User className="w-4 h-4" />
              <span>ID: {user?.id || "-"}</span>
            </div>
            <div className="flex items-center gap-2 text-muted-foreground mt-1">
              <Phone className="w-4 h-4" />
              <span>{user?.phone || "-"}</span>
            </div>
          </div>
        </div>

        <Separator />

        {/* 详细信息 */}
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="username" className="flex items-center gap-2">
              <User className="w-4 h-4 text-muted-foreground" />
              用户名
            </Label>
            <Input
              id="username"
              value={user?.username || "-"}
              disabled
              className="bg-muted/50"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email" className="flex items-center gap-2">
              <Mail className="w-4 h-4 text-muted-foreground" />
              邮箱
            </Label>
            <Input
              id="email"
              type="email"
              value={user?.email || "-"}
              disabled
              className="bg-muted/50"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="nickname" className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-muted-foreground" />
              昵称
            </Label>
            <Input
              id="nickname"
              value={isEditing ? nameInput : user?.nickname || "-"}
              onChange={(e) => onNameChange(e.target.value)}
              disabled={!isEditing}
              className={!isEditing ? "bg-muted/50" : ""}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="phone" className="flex items-center gap-2">
              <Phone className="w-4 h-4 text-muted-foreground" />
              手机号
            </Label>
            <Input
              id="phone"
              value={isEditing ? phoneInput : user?.phone || "-"}
              onChange={(e) => onPhoneChange(e.target.value)}
              disabled={!isEditing}
              className={!isEditing ? "bg-muted/50" : ""}
              placeholder={isEditing ? "请输入手机号" : "-"}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="createdAt" className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-muted-foreground" />
              注册时间
            </Label>
            <Input
              id="createdAt"
              value={formatCreatedAt(user?.createdAt)}
              disabled
              className="bg-muted/50"
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

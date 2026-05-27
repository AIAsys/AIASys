import { useState, useEffect } from "react";
import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";

const AVATAR_COLORS = [
  "bg-blue-500",
  "bg-green-500",
  "bg-purple-500",
  "bg-amber-500",
  "bg-rose-500",
  "bg-teal-500",
  "bg-indigo-500",
  "bg-orange-500",
];

interface ProfileEditDialogProps {
  open: boolean;
  avatarColor: string;
  displayName: string;
  onClose: () => void;
  onSave: (data: { name: string; avatarColor: string; avatarChar: string }) => Promise<boolean>;
}

export function ProfileEditDialog({
  open,
  avatarColor,
  displayName,
  onClose,
  onSave,
}: ProfileEditDialogProps) {
  const [name, setName] = useState(displayName);
  const [color, setColor] = useState(avatarColor || AVATAR_COLORS[0]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setName(displayName);
      setColor(avatarColor || AVATAR_COLORS[0]);
      setError("");
    }
  }, [open, displayName, avatarColor]);

  if (!open) return null;

  const avatarChar = name.trim() ? name.trim().charAt(0).toUpperCase() : "?";

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("昵称不能为空");
      return;
    }
    setSaving(true);
    setError("");
    const ok = await onSave({ name: trimmed, avatarColor: color, avatarChar });
    setSaving(false);
    if (ok) {
      onClose();
    } else {
      setError("保存失败，请重试");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative z-10 mx-4 w-full max-w-sm rounded-xl border border-border bg-background p-6 shadow-lg">
        <div className="mb-5 text-center">
          <h3 className="text-sm font-semibold">编辑个人资料</h3>
        </div>

        <div className="mb-5 flex justify-center">
          <div
            className={cn(
              "flex h-16 w-16 items-center justify-center rounded-full shadow-md transition-colors",
              color,
            )}
          >
            <span className="text-2xl font-semibold text-white">
              {avatarChar}
            </span>
          </div>
        </div>

        <div className="mb-4">
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
            头像颜色
          </label>
          <div className="flex flex-wrap gap-2">
            {AVATAR_COLORS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setColor(c)}
                className={cn(
                  "h-7 w-7 rounded-full transition-all",
                  c,
                  color === c
                    ? "ring-2 ring-offset-2 ring-offset-background ring-foreground scale-110"
                    : "hover:scale-105",
                )}
              />
            ))}
          </div>
        </div>

        <div className="mb-5">
          <label
            htmlFor="profile-nickname"
            className="mb-1.5 block text-xs font-medium text-muted-foreground"
          >
            昵称
          </label>
          <input
            id="profile-nickname"
            type="text"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setError("");
            }}
            maxLength={32}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-tertiary focus:ring-1 focus:ring-tertiary"
          />
        </div>

        {error && (
          <p className="mb-4 text-xs text-destructive">{error}</p>
        )}

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
            取消
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            <Check className="h-4 w-4" />
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}

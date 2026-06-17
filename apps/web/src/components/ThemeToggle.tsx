import { useTheme, type Theme } from "@/contexts/ThemeContext";
import { Sun, Moon, Monitor } from "lucide-react";

const THEME_ORDER: Theme[] = ["light", "dark", "system"];

const THEME_LABEL: Record<Theme, string> = {
  light: "浅色模式",
  dark: "暗色模式",
  system: "跟随系统",
};

const THEME_ARIA: Record<Theme, string> = {
  light: "当前浅色模式",
  dark: "当前暗色模式",
  system: "跟随系统模式",
};

function nextTheme(current: Theme): Theme {
  const idx = THEME_ORDER.indexOf(current);
  return THEME_ORDER[(idx + 1) % THEME_ORDER.length];
}

export function ThemeToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { theme, setTheme } = useTheme();
  const next = nextTheme(theme);

  const icon = (() => {
    switch (theme) {
      case "light":
        return <Sun className={collapsed ? "w-[18px] h-[18px]" : "w-4 h-4"} />;
      case "dark":
        return <Moon className={collapsed ? "w-[18px] h-[18px]" : "w-4 h-4"} />;
      case "system":
        return <Monitor className={collapsed ? "w-[18px] h-[18px]" : "w-4 h-4"} />;
    }
  })();

  const title = `${THEME_LABEL[theme]}（点击切换到${THEME_LABEL[next]}）`;

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setTheme(next)}
        aria-label={THEME_ARIA[theme]}
        title={title}
        className="w-9 h-9 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-sidebar-accent transition-colors"
      >
        {icon}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={THEME_ARIA[theme]}
      title={title}
      className="p-1.5 rounded text-muted-foreground hover:text-sidebar-primary hover:bg-sidebar-accent transition-colors"
    >
      {icon}
    </button>
  );
}

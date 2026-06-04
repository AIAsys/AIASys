import { Button } from "@/components/ui/button";
import { isSingleUserAuthMode } from "@/config/auth";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuthContext } from "@/contexts/AuthContext";
import { ArrowRight, LogOut, Settings, User } from "lucide-react";
import { useState } from "react";
import { Logo } from "./Logo";

import {
  goToAnalysis,
  goToWorkspaceHome,
  navigateWithApp,
  scrollToHomeSection,
  type HomeSectionId,
} from "./navigation";

export const Header = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const { isAuthenticated, isLoading, user, handleLogout } = useAuthContext();
  const isSingleUserMode = isSingleUserAuthMode();
  const resolvedUserLabel = user?.nickname || user?.email || "本地工作区";
  const showAccountMenu = Boolean(user) && (isAuthenticated || isSingleUserMode);

  const navItems: Array<
    | { label: string; type: "section"; target: HomeSectionId }
    | { label: string; type: "route"; target: string }
  > = [
    { label: "能力概览", type: "section", target: "capabilities" },
    { label: "应用场景", type: "section", target: "scenarios" },
    { label: "工作方式", type: "section", target: "workflow" },
  ];

  const handleNavClick = (
    item:
      | { label: string; type: "section"; target: HomeSectionId }
      | { label: string; type: "route"; target: string },
  ) => {
    if (item.type === "section") {
      scrollToHomeSection(item.target);
      return;
    }

    navigateWithApp(item.target);
  };

  return (
    <div className="fixed inset-x-0 top-0 z-50 border-b border-foreground/8 bg-white/78 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.32)] backdrop-blur-2xl supports-[backdrop-filter]:bg-white/66">
      <div className="absolute inset-0 bg-gradient-to-b from-white/95 via-white/78 to-white/62" />
      <header className="relative flex h-16 items-center justify-between container mx-auto px-4 md:h-[4.5rem] md:px-8">
        <button
          type="button"
          onClick={() => navigateWithApp("/home")}
          className="hover:opacity-80 transition-opacity"
          title="首页"
        >
          <Logo className="h-8 w-auto" />
        </button>

        <nav className="hidden lg:flex absolute left-1/2 -translate-x-1/2 items-center justify-center gap-x-8">
          {navItems.map((item) => (
            <button
              type="button"
              key={item.label}
              onClick={() => handleNavClick(item)}
              className="text-[13px] font-medium tracking-[0.01em] text-muted-foreground transition-colors duration-200 hover:text-foreground"
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          {/* GitHub 链接 */}
          <a
            href="https://github.com/AIAsys/AIASys"
            target="_blank"
            rel="noopener noreferrer"
            className="hidden text-muted-foreground transition-colors duration-200 hover:text-foreground md:block"
            title="GitHub"
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="w-5 h-5"
            >
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
            </svg>
          </a>

          <Button
            type="button"
            variant="outline"
            size="sm"
            className="hidden xl:inline-flex h-9"
            onClick={() => goToAnalysis()}
          >
            开始分析
            <ArrowRight className="h-4 w-4" />
          </Button>

          {/* 登录按钮 / 用户菜单 */}
          {showAccountMenu ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="hidden h-9 gap-2 sm:inline-flex"
                >
                  <User className="h-4 w-4" />
                  <span className="hidden sm:inline max-w-[120px] truncate">
                    {resolvedUserLabel}
                  </span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <div className="px-2 py-1.5 text-sm text-muted-foreground border-b mb-1">
                  {resolvedUserLabel}
                </div>
                <DropdownMenuItem onClick={() => window.location.href = "/profile"}>
                  <Settings className="h-4 w-4 mr-2" />
                  设置
                </DropdownMenuItem>
                {!isSingleUserMode ? (
                  <DropdownMenuItem onClick={handleLogout}>
                    <LogOut className="h-4 w-4 mr-2" />
                    登出
                  </DropdownMenuItem>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : !isSingleUserMode && !isLoading ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={goToWorkspaceHome}
              className="hidden h-9 font-mono sm:inline-flex"
            >
              进入工作区
            </Button>
          ) : null}

          {/* 移动端菜单按钮 */}
          <button
            type="button"
            className="md:hidden p-2"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            title="菜单"
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              {mobileMenuOpen ? (
                <>
                  <path d="M18 6L6 18" />
                  <path d="M6 6l12 12" />
                </>
              ) : (
                <>
                  <path d="M3 12h18" />
                  <path d="M3 6h18" />
                  <path d="M3 18h18" />
                </>
              )}
            </svg>
          </button>
        </div>
      </header>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden absolute top-full left-0 w-full bg-background/95 backdrop-blur-sm border-b border-border">
          <nav className="flex flex-col items-center py-6 gap-4">
            {navItems.map((item) => (
              <button
                type="button"
                key={item.label}
                onClick={() => {
                  handleNavClick(item);
                  setMobileMenuOpen(false);
                }}
                className="text-sm font-medium tracking-[0.01em] text-muted-foreground transition-colors duration-200 hover:text-foreground"
              >
                {item.label}
              </button>
            ))}

            <Button
              type="button"
              variant="outline"
              onClick={() => {
                goToAnalysis();
                setMobileMenuOpen(false);
              }}
            >
              开始分析
            </Button>

            {showAccountMenu ? (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    navigateWithApp("/profile");
                    setMobileMenuOpen(false);
                  }}
                >
                  设置
                </Button>
                {!isSingleUserMode ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      handleLogout();
                      setMobileMenuOpen(false);
                    }}
                  >
                    登出
                  </Button>
                ) : null}
              </>
            ) : !isSingleUserMode && !isLoading ? (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  goToWorkspaceHome();
                  setMobileMenuOpen(false);
                }}
              >
                进入工作区
              </Button>
            ) : null}
          </nav>
        </div>
      )}
    </div>
  );
};

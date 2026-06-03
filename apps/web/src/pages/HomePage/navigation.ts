export const homeSectionIds = [
  "surfaces",
  "capabilities",
  "scenarios",
  "workflow",
  "trust",
] as const;

export type HomeSectionId = (typeof homeSectionIds)[number];

function isHomeSectionId(value: string): value is HomeSectionId {
  return homeSectionIds.includes(value as HomeSectionId);
}

export function navigateWithApp(path: string) {
  const withAppNavigate = globalThis as typeof globalThis & {
    appNavigate?: (target: string) => void;
  };

  withAppNavigate.appNavigate?.(path) || (globalThis.location.href = path);
}

export function goToWorkspace(overlay?: string) {
  const query = overlay ? `?overlay=${encodeURIComponent(overlay)}` : "";
  navigateWithApp(`/workspace${query}`);
}

/** @deprecated 使用 goToWorkspace */
export function goToAnalysis(overlay?: string) {
  return goToWorkspace(overlay);
}

export function goToWorkspaceHome() {
  navigateWithApp("/workspace");
}

export function scrollToHomeSection(sectionId: HomeSectionId) {
  const currentPath = globalThis.location.pathname;
  const isHome = currentPath === "/" || currentPath === "/home";

  if (!isHome) {
    const withAppNavigate = globalThis as typeof globalThis & {
      appNavigate?: (target: string) => void;
    };

    if (withAppNavigate.appNavigate) {
      withAppNavigate.appNavigate("/home");
      globalThis.history.replaceState({}, "", `/home#${sectionId}`);
      globalThis.setTimeout(syncHomeHashScroll, 80);
      globalThis.setTimeout(syncHomeHashScroll, 240);
      return;
    }

    globalThis.location.href = `/home#${sectionId}`;
    return;
  }

  globalThis.history.replaceState({}, "", `${currentPath}#${sectionId}`);
  syncHomeHashScroll();
}

export function syncHomeHashScroll() {
  const hash = globalThis.location.hash.replace(/^#/, "");
  if (!hash || !isHomeSectionId(hash)) {
    return;
  }

  const target = globalThis.document.getElementById(hash);
  if (!target) {
    return;
  }

  target.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

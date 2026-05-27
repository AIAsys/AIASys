const WORKSPACE_LIST_REFRESH_EVENT = "aiasys:workspace-list-refresh";

export function emitWorkspaceListRefreshEvent() {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(new CustomEvent(WORKSPACE_LIST_REFRESH_EVENT));
}

export function subscribeWorkspaceListRefresh(
  listener: () => unknown | Promise<unknown>,
) {
  if (typeof window === "undefined") {
    return () => {};
  }

  const handler = () => {
    void listener();
  };

  window.addEventListener(WORKSPACE_LIST_REFRESH_EVENT, handler);
  return () => {
    window.removeEventListener(WORKSPACE_LIST_REFRESH_EVENT, handler);
  };
}

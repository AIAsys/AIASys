import React from "react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** 自定义错误 UI。提供时用其返回值替代默认全屏错误页 */
  fallback?: (error: Error, reset: () => void) => React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("UI 崩溃", error, info);
  }

  handleReload = () => {
    window.location.reload();
  };

  resetError = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const error = this.state.error ?? new Error("发生未知错误");

      if (this.props.fallback) {
        return <>{this.props.fallback(error, this.resetError)}</>;
      }

      return (
        <div className="min-h-screen flex items-center justify-center bg-background text-foreground">
          <div className="max-w-md text-center space-y-3">
            <div className="text-base font-semibold">页面出错</div>
            <div className="text-sm text-muted-foreground break-words">
              {error.message}
            </div>
            <button
              type="button"
              onClick={this.handleReload}
              className="inline-flex items-center justify-center rounded-md bg-black px-4 py-2 text-sm text-white"
            >
              刷新页面
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

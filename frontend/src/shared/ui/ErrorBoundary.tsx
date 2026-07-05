import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center bg-background text-foreground">
          <div className="max-w-md space-y-4">
            <h2 className="text-2xl font-display font-bold tracking-wide">
              Something went wrong
            </h2>
            <p className="text-muted">
              An unexpected error occurred. Please try refreshing the page.
            </p>
            <pre className="text-xs text-left bg-surface-secondary text-foreground p-3 rounded-lg overflow-auto max-h-48 border border-border/50 font-mono">
              {this.state.error.message}
            </pre>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="px-4 py-2 rounded-lg bg-accent text-accent-foreground font-medium hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-metal/40"
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

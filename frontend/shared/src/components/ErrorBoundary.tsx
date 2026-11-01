import { Component, type ErrorInfo, type ReactNode } from "react";

/** Keeps the app usable when one page crashes: shows the error and a retry button. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page error", error, info.componentStack);
  }

  componentDidUpdate(previous: { resetKey?: string }) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card border-l-4 p-6" style={{ borderLeftColor: "var(--critical)" }}>
        <div className="font-semibold text-ink">This view hit an error</div>
        <p className="mt-1 break-all text-sm text-ink2">{this.state.error.message}</p>
        <button className="btn btn-ghost mt-4" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    );
  }
}

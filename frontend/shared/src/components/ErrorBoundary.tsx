import { Component, type ErrorInfo, type ReactNode } from "react";

/** Keeps the app usable when one page crashes: shows the error and a retry button. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  // Error boundaries must be classes: React has no hook for catching rendering errors.
  state: { error: Error | null } = { error: null };

  // React calls this when a child component throws while rendering: keep the error, show the fallback.
  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  // Log the error and the component stack in the browser console (for debugging).
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page error", error, info.componentStack);
  }

  // resetKey changed (e.g. the user opened another page): clear the error and render the page again.
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

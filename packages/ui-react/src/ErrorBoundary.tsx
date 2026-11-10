/**
 * What is shown where a subtree threw.
 *
 * EXTENSIBILITY §7 promises "UI throws → its own error boundary" and
 * nothing provided one. The iframe does protect the *host*: igni's
 * shell survives whatever an extension does. It does not protect the
 * extension from itself. A React tree that throws unmounts, so what
 * an author actually shipped was a blank frame inside a working app —
 * the worst-looking failure available, and the one a partner demo
 * finds.
 *
 * A class, because `componentDidCatch` and
 * `getDerivedStateFromError` have no hook equivalent. This is the
 * only class component under the floor and it is not a style
 * preference.
 *
 * **It catches less than people expect**, and saying so is part of
 * the contract: render, lifecycle and constructor throws, in the
 * subtree below it. Not event handlers, not `setTimeout`, not
 * promise rejections, not anything during SSR. An extension still
 * needs to handle its own async failures — the reference extension's
 * `ScannerClient` is what that looks like.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

/** What an {@link ErrorBoundary} takes. */
export interface ErrorBoundaryProps {
  /** The subtree this boundary guards. */
  children: ReactNode;
  /**
   * Shown instead of the subtree. Receives the error and a function
   * that clears the boundary and remounts the children.
   *
   * The default is deliberately plain and deliberately shows the
   * message: the reader is an extension's user, and "something went
   * wrong" has never once helped anybody report a bug.
   */
  fallback?: (error: Error, reset: () => void) => ReactNode;
  /** Somewhere to send this — a logger, telemetry, a toast. */
  onError?: (error: Error, info: ErrorInfo) => void;
  /**
   * Changing any of these clears the boundary.
   *
   * Without it a boundary that has caught once stays caught forever,
   * so navigating away from the thing that broke shows the error
   * page for the thing that works. Compared by identity, in order,
   * like a hook dependency array.
   */
  resetKeys?: readonly unknown[];
}

interface State {
  error: Error | null;
}

function changed(a: readonly unknown[], b: readonly unknown[]): boolean {
  return a.length !== b.length || a.some((value, i) => !Object.is(value, b[i]));
}

/**
 * What is shown where a subtree threw.
 *
 * See the note at the top of this file: it catches less than people
 * expect, and the default fallback shows the message on purpose.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, State> {
  /**
   * The error the subtree threw, or null while nothing has thrown.
   */
  state: State = { error: null };

  /**
   * The state the boundary holds after a throw.
   *
   * @param error — the error the subtree threw.
   */
  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  /**
   * Reports the error to whoever asked for it.
   *
   * @param error — the error the subtree threw.
   * @param info — React's account of where it was thrown: the component
   *   stack.
   */
  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.props.onError?.(error, info);
  }

  /**
   * Clears the boundary when the reset keys change.
   *
   * @param previous — the props from the previous render, whose
   *   `resetKeys` are compared with the new ones.
   */
  componentDidUpdate(previous: ErrorBoundaryProps): void {
    if (this.state.error === null) return;
    const before = previous.resetKeys ?? [];
    const now = this.props.resetKeys ?? [];
    if (changed(before, now)) this.reset();
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  /**
   * The children, or the error page when the subtree threw.
   */
  render(): ReactNode {
    const { error } = this.state;
    if (error === null) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);
    return (
      <div className="ui-crash" role="alert">
        <p className="ui-text">Something in this view stopped working.</p>
        <pre className="ui-crash-detail">{error.message}</pre>
        <button type="button" className="btn" onClick={this.reset}>
          Try again
        </button>
      </div>
    );
  }
}

/** The release list, loaded once and again whenever it is asked to refresh. */

import { useCallback, useEffect, useState } from "react";

import { messageOf, type NotesClient, type Release } from "./notes";

export type ReleaseLoad =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | {
      state: "ready";
      releases: Release[];
      /** Why the last refresh failed, while the list before it stays on screen. */
      refreshError: string | null;
    };

export interface Releases {
  load: ReleaseLoad;
  /** Fetch the list again, keeping the current one on screen meanwhile. */
  refresh: () => void;
}

export function useReleases(client: NotesClient): Releases {
  const [load, setLoad] = useState<ReleaseLoad>({ state: "loading" });
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    let alive = true;
    client.releases().then(
      (releases) => {
        if (alive) setLoad({ state: "ready", releases, refreshError: null });
      },
      (error: unknown) => {
        if (!alive) return;
        const message = messageOf(error);
        // A list already on screen is kept: a failed refresh says so
        // rather than emptying the pane beside what it was refreshing for.
        setLoad((current) =>
          current.state === "ready" ? { ...current, refreshError: message } : { state: "failed", message },
        );
      },
    );
    return () => {
      alive = false;
    };
  }, [client, generation]);

  const refresh = useCallback(() => setGeneration((n) => n + 1), []);
  return { load, refresh };
}

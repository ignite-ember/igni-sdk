/** Functions following one value: added, removed, and told of a change. */
export class Watchers<T> {
  private readonly fns = new Set<(value: T) => void>();

  /** Follow the value. Returns an unsubscribe. */
  add(fn: (value: T) => void): () => void {
    this.fns.add(fn);
    return () => {
      this.fns.delete(fn);
    };
  }

  /** Tell every watcher the value is now `value`. */
  emit(value: T): void {
    for (const fn of this.fns) fn(value);
  }
}

// How long to wait between attempts to open igni's socket.

/** `attempts` waits, starting at `first` seconds and doubling up to `most`. */
export class Backoff {
  readonly attempts: number;
  readonly first: number;
  readonly most: number;

  constructor(opts: { attempts?: number; first?: number; most?: number } = {}) {
    this.attempts = opts.attempts ?? 5;
    this.first = opts.first ?? 0.5;
    this.most = opts.most ?? 8.0;
  }

  /** The waits, in seconds. */
  *delays(): IterableIterator<number> {
    let delay = this.first;
    for (let i = 0; i < this.attempts; i++) {
      yield delay;
      delay = Math.min(delay * 2, this.most);
    }
  }
}

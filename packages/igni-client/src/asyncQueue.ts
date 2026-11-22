// A minimal unbounded async queue and a deferred, standing in for the pieces of
// Python's asyncio this client leans on.

/** An unbounded FIFO queue whose `get()` waits for the next `put()`. */
export class AsyncQueue<T> {
  private items: T[] = [];
  private waiters: Array<(value: T) => void> = [];

  put(item: T): void {
    const waiter = this.waiters.shift();
    if (waiter) {
      waiter(item);
    } else {
      this.items.push(item);
    }
  }

  get(): Promise<T> {
    const item = this.items.shift();
    if (item !== undefined) {
      return Promise.resolve(item);
    }
    return new Promise<T>((resolve) => this.waiters.push(resolve));
  }

  get empty(): boolean {
    return this.items.length === 0;
  }
}

/** A promise with its `resolve`/`reject` exposed. */
export class Deferred<T> {
  readonly promise: Promise<T>;
  resolve!: (value: T) => void;
  reject!: (reason: unknown) => void;
  private settled = false;

  constructor() {
    this.promise = new Promise<T>((resolve, reject) => {
      this.resolve = (value: T) => {
        if (!this.settled) {
          this.settled = true;
          resolve(value);
        }
      };
      this.reject = (reason: unknown) => {
        if (!this.settled) {
          this.settled = true;
          reject(reason);
        }
      };
    });
    // Swallow "unhandled rejection" for a deferred nobody awaits yet.
    this.promise.catch(() => undefined);
  }

  get done(): boolean {
    return this.settled;
  }
}

/** Sleep for `seconds`. */
export function sleep(seconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, seconds * 1000));
}

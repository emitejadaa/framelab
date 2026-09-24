export interface Emitter<T extends unknown[]> {
  on(cb: (...args: T) => void): () => void;
  emit(...args: T): void;
  clear(): void;
}

export function createEmitter<T extends unknown[]>(): Emitter<T> {
  const listeners = new Set<(...args: T) => void>();
  return {
    on(cb) {
      listeners.add(cb);
      return () => {
        listeners.delete(cb);
      };
    },
    emit(...args) {
      for (const cb of Array.from(listeners)) cb(...args); // copy: callbacks may unsubscribe
    },
    clear() {
      listeners.clear();
    },
  };
}

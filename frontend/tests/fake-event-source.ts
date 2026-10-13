type Listener = (event: MessageEvent<string>) => void;

/** Hand-written stand-in for the browser EventSource, which jsdom does not provide. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  closed = false;
  private listeners = new Map<string, Listener[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, payload?: unknown): void {
    if (this.closed) return;
    const data = payload === undefined ? "" : JSON.stringify(payload);
    for (const listener of this.listeners.get(type) ?? []) {
      listener(new MessageEvent(type, { data }));
    }
  }

  static reset(): void {
    FakeEventSource.instances = [];
  }
}

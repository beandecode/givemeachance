/** jsdom has no layout: this gives `window.matchMedia` a fake window width that tests can change. */
const DEFAULT_WIDTH = 1280;
let width = DEFAULT_WIDTH;
const lists = new Set<{ query: string; matches: boolean; notify: () => void }>();

function evaluate(query: string): boolean {
  const min = /\(min-width:\s*(\d+)px\)/.exec(query);
  const max = /\(max-width:\s*(\d+)px\)/.exec(query);
  return (!min || width >= Number(min[1])) && (!max || width <= Number(max[1]));
}

export function mockViewport(next: number) {
  width = next;
  window.innerWidth = next;
  for (const entry of lists) {
    const now = evaluate(entry.query);
    if (now !== entry.matches) {
      entry.matches = now;
      entry.notify();
    }
  }
}

export function resetViewport() {
  mockViewport(DEFAULT_WIDTH);
}

export function installMatchMedia() {
  window.matchMedia = (query: string) => {
    const handlers = new Set<() => void>();
    const entry = { query, matches: evaluate(query), notify: () => handlers.forEach((handler) => handler()) };
    lists.add(entry);
    return {
      get matches() {
        return entry.matches;
      },
      media: query,
      onchange: null,
      addEventListener: (_type: string, handler: () => void) => handlers.add(handler),
      removeEventListener: (_type: string, handler: () => void) => handlers.delete(handler),
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    } as unknown as MediaQueryList;
  };
}

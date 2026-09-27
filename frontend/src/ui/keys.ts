/**
 * Whether a key event is a widget's own shortcut: it happened inside that widget's `.fl-root`
 * (several widgets can share a notebook page), nothing handled it yet and it was not typed into a
 * field. composedPath() sees through a shadow root, where `target` is retargeted to the host.
 */
export function isShortcut(e: KeyboardEvent, inside: Element | null): boolean {
  const root = inside?.closest(".fl-root");
  if (!root || e.defaultPrevented) return false;
  const path = e.composedPath();
  if (!path.includes(root)) return false;
  const target = path[0];
  return !(target instanceof Element && target.closest("input, textarea, select, [contenteditable]"));
}

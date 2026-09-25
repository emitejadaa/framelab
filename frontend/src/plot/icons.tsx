/** Tiny chart pictograms for the gallery (drawn with currentColor). */
import type { ReactElement } from "react";
const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

const SHAPES: Record<string, ReactElement> = {
  line: <polyline {...P} points="3,19 10,11 16,14 25,5 33,9" />,
  scatter: (
    <g fill="currentColor">
      {[[6, 17], [10, 12], [14, 15], [18, 8], [23, 11], [27, 6], [31, 9], [12, 19]].map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="1.6" />
      ))}
    </g>
  ),
  bar: (
    <g fill="currentColor">
      <rect x="5" y="10" width="5" height="11" rx="1" />
      <rect x="13" y="5" width="5" height="16" rx="1" />
      <rect x="21" y="13" width="5" height="8" rx="1" />
      <rect x="29" y="8" width="4" height="13" rx="1" />
    </g>
  ),
  barh: (
    <g fill="currentColor">
      <rect x="4" y="3" width="22" height="4" rx="1" />
      <rect x="4" y="9" width="14" height="4" rx="1" />
      <rect x="4" y="15" width="28" height="4" rx="1" />
    </g>
  ),
  hist: (
    <g fill="currentColor">
      {[[4, 16], [9, 11], [14, 5], [19, 8], [24, 13], [29, 17]].map(([x, y]) => (
        <rect key={x} x={x} y={y} width="5" height={21 - y} />
      ))}
    </g>
  ),
  box: (
    <g {...P}>
      <line x1="10" y1="3" x2="10" y2="21" />
      <rect x="6" y="7" width="8" height="9" fill="currentColor" fillOpacity=".25" />
      <line x1="24" y1="5" x2="24" y2="19" />
      <rect x="20" y="9" width="8" height="6" fill="currentColor" fillOpacity=".25" />
    </g>
  ),
  violin: (
    <g {...P} fill="currentColor" fillOpacity=".25">
      <path d="M11 3 C4 9, 17 11, 8 15 C5 17, 17 19, 11 21 C5 19, 17 17, 14 15 C5 11, 18 9, 11 3Z" />
      <path d="M25 3 C21 8, 29 12, 22 16 C20 18, 30 19, 25 21 C20 19, 30 18, 28 16 C21 12, 29 8, 25 3Z" />
    </g>
  ),
  pie: (
    <g {...P}>
      <circle cx="18" cy="12" r="9" />
      <path d="M18 12 L18 3 M18 12 L26 16 M18 12 L10 17" />
    </g>
  ),
  area: (
    <g>
      <path d="M3 21 L3 14 L11 9 L19 12 L27 5 L33 8 L33 21Z" fill="currentColor" fillOpacity=".3" />
      <path d="M3 21 L3 18 L11 15 L19 17 L27 12 L33 14 L33 21Z" fill="currentColor" fillOpacity=".55" />
    </g>
  ),
  step: <polyline {...P} points="3,18 9,18 9,12 16,12 16,15 23,15 23,6 33,6" />,
  hexbin: (
    <g fill="currentColor">
      {[[8, 8, 0.3], [15, 8, 0.7], [22, 8, 0.45], [11.5, 14, 0.9], [18.5, 14, 0.55], [25.5, 14, 0.25], [15, 20, 0.35]].map(
        ([x, y, o]) => (
          <polygon key={`${x}-${y}`} opacity={o} points={`${x},${y - 3.5} ${x + 3},${y - 1.7} ${x + 3},${y + 1.7} ${x},${y + 3.5} ${x - 3},${y + 1.7} ${x - 3},${y - 1.7}`} />
        ),
      )}
    </g>
  ),
  heatmap: (
    <g fill="currentColor">
      {[0, 1, 2].flatMap((r) =>
        [0, 1, 2, 3].map((c) => (
          <rect key={`${r}-${c}`} x={5 + c * 7} y={3 + r * 6.3} width="6" height="5.5" opacity={0.2 + ((r * 4 + c) * 0.37) % 0.8} />
        )),
      )}
    </g>
  ),
};

export function KindIcon({ kind }: { kind: string }) {
  return (
    <svg viewBox="0 0 36 24" width="36" height="24" aria-hidden="true" className="fl-kind-icon">
      {SHAPES[kind] ?? SHAPES.line}
    </svg>
  );
}

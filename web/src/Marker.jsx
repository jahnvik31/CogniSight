import { For, Show } from "solid-js";
import { MARKER_BITS } from "./markers";

// One ArUco 4x4 marker as an SVG. The grid is 6x6 cells: a one-cell black border
// around the 4x4 bits, where "1" is white and "0" is black. `quiet` adds that many
// cells of white margin on every side, which the camera needs to find the edge.
//
// props.id: marker number (0–49). props.size: CSS width and height, such as "48px"
// or "140mm" (the 6x6 marker itself is size × 6 / (6 + 2 × quiet)). props.quiet:
// white margin in cells, default 1. props.label: accessible name; without one the
// marker is decorative. props.x / props.y: position when nested in another SVG.
export default function Marker(props) {
  const quiet = () => (Number.isFinite(props.quiet) && props.quiet >= 0 ? props.quiet : 1);
  const bits = () => (Number.isInteger(props.id) ? MARKER_BITS[props.id] : undefined);
  const cells = () => {
    const b = bits();
    if (!b) return [];
    const out = [];
    for (let i = 0; i < 16; i++) if (b[i] === "1") out.push({ x: 1 + (i % 4), y: 1 + Math.floor(i / 4) });
    return out;
  };
  const span = () => 6 + quiet() * 2;

  return (
    <svg
      class={`marker-svg ${props.class || ""}`}
      viewBox={`${-quiet()} ${-quiet()} ${span()} ${span()}`}
      width={props.size}
      height={props.size}
      x={props.x}
      y={props.y}
      shape-rendering="crispEdges"
      role={props.label ? "img" : undefined}
      aria-label={props.label || undefined}
      aria-hidden={props.label ? undefined : "true"}
      focusable="false"
    >
      <rect x={-quiet()} y={-quiet()} width={span()} height={span()} fill="#ffffff" />
      <Show
        when={bits()}
        fallback={
          <rect x="0.15" y="0.15" width="5.7" height="5.7" fill="none" stroke="#5d6b6e" stroke-width="0.3" stroke-dasharray="0.6 0.4" />
        }
      >
        <rect x="0" y="0" width="6" height="6" fill="#000000" />
        <For each={cells()}>{(c) => <rect x={c.x} y={c.y} width="1" height="1" fill="#ffffff" />}</For>
      </Show>
    </svg>
  );
}

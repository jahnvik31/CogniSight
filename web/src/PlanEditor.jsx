import { batch, createEffect, createMemo, createSignal, For, Index, on, onCleanup, onMount, Show } from "solid-js";
import { useBeforeLeave } from "@solidjs/router";
import { offline, savePlan } from "./api";
import Marker from "./Marker";
import { normalizePlan, PLAN_LIMITS, round2, routePairs, signName } from "./signs";
import {
  DoorToolIcon,
  FitIcon,
  LabelToolIcon,
  PanToolIcon,
  RotateIcon,
  SelectToolIcon,
  SignToolIcon,
  UndoIcon,
  WallToolIcon,
  ZoomInIcon,
  ZoomOutIcon,
} from "./icons";

// The floor plan, in metres. Origin top-left, y down, angles in degrees with 0
// pointing right and 90 pointing down (docs/API.md, "Home").
const GRID = 0.5;
const ZONE_ANGLE = 70; // How wide the camera can read a sign from, in degrees.
const ZONE_LENGTH = 2.5; // How far away it can read a 14 cm sign, in metres (measured limit of the detector).
const SIGN_OFFSET = 0.08; // Signs sit just off the wall, on the reading side.
const MIN_WALL = 0.25;
const UNDO_LIMIT = 100;
const DOOR_WIDTHS = [0.7, 0.8, 0.9, 1, 1.2];

const LISTS = { wall: "walls", door: "doors", label: "labels", sign: "signs" };

const TOOLS = [
  { id: "select", label: "Select", Icon: SelectToolIcon },
  { id: "wall", label: "Wall", Icon: WallToolIcon },
  { id: "door", label: "Door", Icon: DoorToolIcon },
  { id: "label", label: "Room name", Icon: LabelToolIcon },
  { id: "sign", label: "Place sign", Icon: SignToolIcon },
  { id: "pan", label: "Pan", Icon: PanToolIcon },
];

const HINTS = {
  select: "Tap an item to select it, then drag to move it. Drag empty space to move the view.",
  wall: "Press and drag to draw a wall. Hold Shift for 45° angles.",
  door: "Tap on or near a wall to put a door in it.",
  label: "Tap inside a room to name it.",
  sign: "Choose a sign, then tap beside the wall where it will hang. It turns to face into the room.",
  pan: "Drag to move the view.",
};

const snap = (v) => Math.round(v / GRID) * GRID;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const rad = (d) => (d * Math.PI) / 180;
const toDeg = (r) => (((r * 180) / Math.PI) % 360 + 360) % 360;
const normAngle = (a) => ((Math.round(a) % 360) + 360) % 360;

function nearestWall(walls, p) {
  let best = null;
  walls.forEach((w, index) => {
    const dx = w.x2 - w.x1;
    const dy = w.y2 - w.y1;
    const len = Math.hypot(dx, dy);
    if (len === 0) return;
    const t = clamp(((p.x - w.x1) * dx + (p.y - w.y1) * dy) / (len * len), 0, 1);
    const x = w.x1 + t * dx;
    const y = w.y1 + t * dy;
    const d = Math.hypot(p.x - x, p.y - y);
    if (!best || d < best.d) best = { index, wall: w, t, x, y, d, len, ux: dx / len, uy: dy / len };
  });
  return best;
}

// A door centred where the wall was tapped, kept inside the wall, aligned with it.
function doorOnWall(hit, width) {
  const w = Math.min(width, hit.len);
  let along = Math.round((hit.t * hit.len) / 0.05) * 0.05;
  along = hit.len > w ? clamp(along, w / 2, hit.len - w / 2) : hit.len / 2;
  return {
    x: round2(hit.wall.x1 + hit.ux * along),
    y: round2(hit.wall.y1 + hit.uy * along),
    angle: normAngle(toDeg(Math.atan2(hit.uy, hit.ux))),
    width: round2(w),
  };
}

// A sign against the wall, on the side that was tapped, facing away from the wall.
function signOnWall(hit, p) {
  let nx = -hit.uy;
  let ny = hit.ux;
  if ((p.x - hit.x) * nx + (p.y - hit.y) * ny < 0) {
    nx = -nx;
    ny = -ny;
  }
  return {
    x: round2(hit.x + nx * SIGN_OFFSET),
    y: round2(hit.y + ny * SIGN_OFFSET),
    facing: normAngle(toDeg(Math.atan2(ny, nx))),
  };
}

function wedge(x, y, facing) {
  const a1 = rad(facing - ZONE_ANGLE / 2);
  const a2 = rad(facing + ZONE_ANGLE / 2);
  const r = ZONE_LENGTH;
  return `M${x} ${y}L${x + r * Math.cos(a1)} ${y + r * Math.sin(a1)}A${r} ${r} 0 0 1 ${x + r * Math.cos(a2)} ${
    y + r * Math.sin(a2)
  }Z`;
}

function niceLength(scale) {
  for (const m of [0.5, 1, 2, 5, 10, 20]) if (m * scale >= 56) return m;
  return 20;
}

const isTyping = (el) => el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName);

export default function PlanEditor(props) {
  let svg;
  let labelInput;

  // The plan being edited, the last saved copy, and the undo stack. Every change
  // makes new objects, so earlier snapshots can be kept without copying.
  const [plan, setPlan] = createSignal(normalizePlan(null));
  const [savedJson, setSavedJson] = createSignal("");
  const [loaded, setLoaded] = createSignal(false);
  const [undoStack, setUndoStack] = createSignal([]);
  const dirty = createMemo(() => loaded() && JSON.stringify(plan()) !== savedJson());

  const [tool, setTool] = createSignal("select");
  const [selected, setSelected] = createSignal(null); // { kind, index }
  const [armed, setArmed] = createSignal(null); // sign id for the Place sign tool
  const [draft, setDraft] = createSignal(null); // wall being drawn

  const [size, setSize] = createSignal({ w: 0, h: 0 });
  const [view, setView] = createSignal({ cx: 6, cy: 4.5, scale: 40 });
  let fitted = false;

  const [saving, setSaving] = createSignal(false);
  const [notice, setNotice] = createSignal("");
  const [error, setError] = createSignal("");

  // Pointer input. One finger or the mouse edits; two fingers move and zoom.
  const pointers = new Map();
  let action = null;

  // Taking in the device's plan: once at the start, and later only when there
  // are no unsaved changes here (a sign deleted elsewhere drops off the plan).
  createEffect(
    on(
      () => props.plan,
      (incoming) => {
        if (incoming === undefined) return;
        const next = normalizePlan(incoming);
        const json = JSON.stringify(next);
        if (!loaded() || (!dirty() && !action && json !== savedJson())) {
          batch(() => {
            setPlan(next);
            setSavedJson(json);
            setLoaded(true);
          });
        }
      },
    ),
  );

  const signById = createMemo(() => new Map((props.signs || []).map((s) => [s.id, s])));
  const placedIds = createMemo(() => new Set(plan().signs.map((s) => s.sign)));

  function commit(next) {
    setUndoStack((stack) => [...stack.slice(-(UNDO_LIMIT - 1)), plan()]);
    setPlan(next);
  }

  function undo() {
    const stack = undoStack();
    if (!stack.length) return;
    batch(() => {
      setPlan(stack[stack.length - 1]);
      setUndoStack(stack.slice(0, -1));
      setSelected(null);
      setNotice("Undone.");
    });
  }

  const withItem = (p, kind, index, item) => ({
    ...p,
    [LISTS[kind]]: p[LISTS[kind]].map((x, i) => (i === index ? item : x)),
  });
  const withoutItem = (p, kind, index) => ({ ...p, [LISTS[kind]]: p[LISTS[kind]].filter((_, i) => i !== index) });

  const selItem = () => {
    const s = selected();
    return s ? plan()[LISTS[s.kind]]?.[s.index] : undefined;
  };
  createEffect(() => {
    if (selected() && !selItem()) setSelected(null);
  });

  // Unsaved changes: ask before leaving, both inside the dashboard and for the browser.
  useBeforeLeave((e) => {
    if (!dirty() || e.defaultPrevented) return;
    e.preventDefault();
    setTimeout(() => {
      if (window.confirm("The floor plan has changes that aren't saved. Leave without saving them?")) e.retry(true);
    }, 0);
  });
  const beforeUnload = (e) => {
    if (!dirty()) return;
    e.preventDefault();
    e.returnValue = "";
  };
  window.addEventListener("beforeunload", beforeUnload);
  onCleanup(() => window.removeEventListener("beforeunload", beforeUnload));

  // View: centre in metres and scale in pixels per metre.
  function fitScale() {
    const { w, h } = size();
    const p = plan();
    if (!w || !h) return 40;
    const pad = 0.8;
    return Math.min(w / (p.width + pad * 2), h / (p.height + pad * 2));
  }
  const minScale = () => Math.max(4, fitScale() * 0.5);
  const maxScale = 240;

  function fit() {
    const p = plan();
    setView({ cx: p.width / 2, cy: p.height / 2, scale: fitScale() });
  }

  function zoomBy(factor, client) {
    const v = view();
    const scale = clamp(v.scale * factor, minScale(), maxScale);
    if (!client || !svg) {
      setView({ ...v, scale });
      return;
    }
    const rect = svg.getBoundingClientRect();
    const { w, h } = size();
    const ox = client.x - rect.left - w / 2;
    const oy = client.y - rect.top - h / 2;
    const px = v.cx + ox / v.scale;
    const py = v.cy + oy / v.scale;
    setView({ cx: px - ox / scale, cy: py - oy / scale, scale });
  }

  createEffect(() => {
    if (!fitted && loaded() && size().w > 0) {
      fitted = true;
      fit();
    }
  });

  const viewBox = () => {
    const { w, h } = size();
    const v = view();
    if (!w || !h) return `0 0 ${plan().width} ${plan().height}`;
    return `${v.cx - w / 2 / v.scale} ${v.cy - h / 2 / v.scale} ${w / v.scale} ${h / v.scale}`;
  };

  // Sizes that should stay readable on screen at any zoom, in metres.
  const px = (n) => n / view().scale;
  const iconSize = () => Math.max(0.45, px(26));
  const textSize = () => Math.max(0.3, px(13));
  const labelSize = () => Math.max(0.4, px(15));

  onMount(() => {
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize({ w: width, h: height });
    });
    observer.observe(svg);
    // Trackpad pinch arrives as ctrl + wheel. A plain wheel still scrolls the page.
    const onWheel = (e) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      zoomBy(Math.exp(-e.deltaY * 0.01), { x: e.clientX, y: e.clientY });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    onCleanup(() => {
      observer.disconnect();
      svg.removeEventListener("wheel", onWheel);
    });
  });

  // Signs: the Home page can ask the editor to place a sign that was just added.
  createEffect(
    on(
      () => props.arm,
      (request) => {
        if (!request) return;
        batch(() => {
          setTool("sign");
          setArmed(request.id);
          setSelected(null);
        });
      },
      { defer: true },
    ),
  );

  createEffect(() => {
    if (tool() !== "sign") return;
    const current = armed();
    if (current !== null && signById().has(current)) return;
    const list = props.signs || [];
    const next = list.find((s) => !placedIds().has(s.id)) || list[0];
    setArmed(next ? next.id : null);
  });

  function chooseTool(id) {
    batch(() => {
      setTool(id);
      setDraft(null);
      if (id !== "select") setSelected(null);
      setNotice("");
    });
  }

  function toPlan(client) {
    const rect = svg.getBoundingClientRect();
    const { w, h } = size();
    const v = view();
    return { x: v.cx + (client.x - rect.left - w / 2) / v.scale, y: v.cy + (client.y - rect.top - h / 2) / v.scale };
  }

  const inside = (p) => ({ x: clamp(p.x, 0, plan().width), y: clamp(p.y, 0, plan().height) });
  const snapPoint = (p) => inside({ x: snap(p.x), y: snap(p.y) });

  function wallEnd(start, raw, straight) {
    if (!straight) return snapPoint(raw);
    const dx = raw.x - start.x;
    const dy = raw.y - start.y;
    const angle = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
    let len = dx * Math.cos(angle) + dy * Math.sin(angle);
    len = Math.max(0, Math.round(len / GRID) * GRID);
    return inside({ x: round2(start.x + len * Math.cos(angle)), y: round2(start.y + len * Math.sin(angle)) });
  }

  const reach = (metres, pixels) => Math.max(metres, px(pixels));

  function cancelAction() {
    if (!action) return;
    if (action.type === "drag" && action.moved) {
      setPlan(action.before);
      setUndoStack((stack) => stack.slice(0, -1));
    }
    if (action.type === "wall") setDraft(null);
    action = null;
  }

  function startGesture() {
    const [a, b] = [...pointers.values()];
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    action = {
      type: "gesture",
      anchor: toPlan(mid),
      dist: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)),
      scale: view().scale,
    };
  }

  function onPointerDown(e) {
    if (e.pointerType === "mouse" && e.button !== 0 && e.button !== 1) return;
    e.preventDefault();
    svg.focus({ preventScroll: true });
    // A new first finger or mouse press: anything left over from before is stale.
    if (e.isPrimary) {
      cancelAction();
      pointers.clear();
    }
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    try {
      svg.setPointerCapture(e.pointerId);
    } catch {
      // Not every browser allows capture here; dragging still works inside the plan.
    }
    if (pointers.size === 2) {
      cancelAction();
      startGesture();
      return;
    }
    if (pointers.size > 2 || action) return;

    const client = { x: e.clientX, y: e.clientY };
    const p = toPlan(client);
    const startPan = () => {
      action = { type: "pan", client, from: view() };
    };
    if (e.button === 1 || tool() === "pan") return startPan();

    if (tool() === "select") {
      const target = e.target.closest?.("[data-kind]");
      if (!target) {
        setSelected(null);
        return startPan();
      }
      const kind = target.getAttribute("data-kind");
      const index = Number(target.getAttribute("data-index"));
      const handle = Number(target.getAttribute("data-handle")) || 0;
      setSelected({ kind, index });
      const orig = plan()[LISTS[kind]]?.[index];
      if (!orig) return;
      action = { type: "drag", kind, index, handle, orig, start: p, client, before: plan(), moved: false };
      return;
    }

    if (tool() === "wall") {
      if (plan().walls.length >= PLAN_LIMITS.walls) {
        setNotice(`The plan already has ${PLAN_LIMITS.walls} walls, the most it can hold.`);
        return;
      }
      const start = snapPoint(p);
      action = { type: "wall", start };
      setDraft({ x1: start.x, y1: start.y, x2: start.x, y2: start.y });
      return;
    }

    action = { type: "tap", client };
  }

  function onPointerMove(e) {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (!action) return;
    const client = { x: e.clientX, y: e.clientY };

    if (action.type === "gesture") {
      if (pointers.size < 2) return;
      const [a, b] = [...pointers.values()];
      const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      const dist = Math.max(1, Math.hypot(a.x - b.x, a.y - b.y));
      const scale = clamp((action.scale * dist) / action.dist, minScale(), maxScale);
      const rect = svg.getBoundingClientRect();
      const { w, h } = size();
      setView({
        cx: action.anchor.x - (mid.x - rect.left - w / 2) / scale,
        cy: action.anchor.y - (mid.y - rect.top - h / 2) / scale,
        scale,
      });
      return;
    }

    if (action.type === "pan") {
      const from = action.from;
      setView({
        ...from,
        cx: from.cx - (client.x - action.client.x) / from.scale,
        cy: from.cy - (client.y - action.client.y) / from.scale,
      });
      return;
    }

    if (action.type === "tap") {
      if (Math.hypot(client.x - action.client.x, client.y - action.client.y) > 10) action.moved = true;
      return;
    }

    const p = toPlan(client);

    if (action.type === "wall") {
      const end = wallEnd(action.start, p, e.shiftKey);
      setDraft({ x1: action.start.x, y1: action.start.y, x2: end.x, y2: end.y });
      return;
    }

    if (action.type === "drag") {
      if (!action.moved) {
        if (Math.hypot(client.x - action.client.x, client.y - action.client.y) < 4) return;
        action.moved = true;
        setUndoStack((stack) => [...stack.slice(-(UNDO_LIMIT - 1)), action.before]);
      }
      const { kind, index, orig, start, handle } = action;
      const dx = p.x - start.x;
      const dy = p.y - start.y;
      const current = plan();
      let item;
      if (kind === "wall") {
        if (handle) {
          const fixed = handle === 1 ? { x: orig.x2, y: orig.y2 } : { x: orig.x1, y: orig.y1 };
          const end = wallEnd(fixed, p, e.shiftKey);
          item = handle === 1 ? { ...orig, x1: end.x, y1: end.y } : { ...orig, x2: end.x, y2: end.y };
        } else {
          const W = current.width;
          const H = current.height;
          const sx = clamp(snap(dx), -Math.min(orig.x1, orig.x2), W - Math.max(orig.x1, orig.x2));
          const sy = clamp(snap(dy), -Math.min(orig.y1, orig.y2), H - Math.max(orig.y1, orig.y2));
          item = { x1: round2(orig.x1 + sx), y1: round2(orig.y1 + sy), x2: round2(orig.x2 + sx), y2: round2(orig.y2 + sy) };
        }
      } else if (kind === "door") {
        const c = inside({ x: orig.x + dx, y: orig.y + dy });
        const hit = nearestWall(current.walls, c);
        item = hit && hit.d <= reach(0.6, 20) ? doorOnWall(hit, orig.width) : { ...orig, ...snapPoint(c) };
      } else if (kind === "sign") {
        const c = inside({ x: orig.x + dx, y: orig.y + dy });
        const hit = nearestWall(current.walls, c);
        item = hit && hit.d <= reach(0.6, 20) ? { ...orig, ...signOnWall(hit, c) } : { ...orig, ...snapPoint(c) };
      } else {
        item = { ...orig, ...snapPoint({ x: orig.x + dx, y: orig.y + dy }) };
      }
      setPlan(withItem(current, kind, index, item));
    }
  }

  function onPointerUp(e) {
    if (!pointers.has(e.pointerId)) return;
    pointers.delete(e.pointerId);
    if (!action) return;
    if (action.type === "gesture") {
      // Wait until every finger has lifted before starting anything new.
      if (pointers.size === 0) action = null;
      return;
    }
    if (e.type !== "pointerup") {
      cancelAction();
      return;
    }
    const finished = action;
    action = null;
    const p = toPlan({ x: e.clientX, y: e.clientY });

    if (finished.type === "wall") {
      const d = draft();
      setDraft(null);
      if (d && Math.hypot(d.x2 - d.x1, d.y2 - d.y1) >= MIN_WALL) {
        const wall = { x1: round2(d.x1), y1: round2(d.y1), x2: round2(d.x2), y2: round2(d.y2) };
        commit({ ...plan(), walls: [...plan().walls, wall] });
        setNotice(`Wall added, ${formatMetres(Math.hypot(d.x2 - d.x1, d.y2 - d.y1))} long.`);
      }
      return;
    }

    if (finished.type === "tap" && !finished.moved) placeAt(p);
  }

  function placeAt(raw) {
    const p = inside(raw);
    const current = plan();
    if (tool() === "door") {
      const hit = nearestWall(current.walls, p);
      if (!hit || hit.d > reach(0.75, 24)) {
        setNotice(current.walls.length ? "Tap on or near a wall to put a door in it." : "Draw the walls first, then add doors.");
        return;
      }
      if (current.doors.length >= PLAN_LIMITS.doors) {
        setNotice(`The plan already has ${PLAN_LIMITS.doors} doors, the most it can hold.`);
        return;
      }
      commit({ ...current, doors: [...current.doors, doorOnWall(hit, 0.9)] });
      setNotice("Door added.");
      return;
    }

    if (tool() === "label") {
      if (current.labels.length >= PLAN_LIMITS.labels) {
        setNotice(`The plan already has ${PLAN_LIMITS.labels} room names, the most it can hold.`);
        return;
      }
      const label = { ...snapPoint(p), text: "Room" };
      commit({ ...current, labels: [...current.labels, label] });
      batch(() => {
        setTool("select");
        setSelected({ kind: "label", index: current.labels.length });
        setNotice("Room name added. Type the name of the room.");
      });
      queueMicrotask(() => {
        labelInput?.focus();
        labelInput?.select();
      });
      return;
    }

    if (tool() === "sign") {
      const id = armed();
      const sign = signById().get(id);
      if (!sign) {
        setNotice((props.signs || []).length ? "Choose a sign to place first." : "Add a sign first, then place it here.");
        return;
      }
      const hit = nearestWall(current.walls, p);
      const spot = hit && hit.d <= reach(1.5, 24) ? signOnWall(hit, p) : { ...snapPoint(p), facing: 90 };
      const existing = current.signs.findIndex((s) => s.sign === id);
      const placed = { sign: id, ...spot };
      const signs =
        existing >= 0 ? current.signs.map((s, i) => (i === existing ? placed : s)) : [...current.signs, placed];
      commit({ ...current, signs });
      setNotice(`${signName(sign)} ${existing >= 0 ? "moved" : "placed"}. The shaded area shows where they can stand to read it.`);
      const next = (props.signs || []).find((s) => s.id !== id && !signs.some((x) => x.sign === s.id));
      if (next) setArmed(next.id);
    }
  }

  // Changes to the selected item, from the bar or the keyboard.
  function moveSelected(dx, dy) {
    const s = selected();
    const item = selItem();
    if (!s || !item) return;
    const p = plan();
    let next;
    if (s.kind === "wall") {
      const sx = clamp(dx, -Math.min(item.x1, item.x2), p.width - Math.max(item.x1, item.x2));
      const sy = clamp(dy, -Math.min(item.y1, item.y2), p.height - Math.max(item.y1, item.y2));
      next = { x1: round2(item.x1 + sx), y1: round2(item.y1 + sy), x2: round2(item.x2 + sx), y2: round2(item.y2 + sy) };
    } else {
      next = { ...item, x: round2(clamp(item.x + dx, 0, p.width)), y: round2(clamp(item.y + dy, 0, p.height)) };
    }
    commit(withItem(p, s.kind, s.index, next));
  }

  function rotateSelected() {
    const s = selected();
    const item = selItem();
    if (!s || !item) return;
    if (s.kind === "door") commit(withItem(plan(), "door", s.index, { ...item, angle: normAngle(item.angle + 90) }));
    if (s.kind === "sign") commit(withItem(plan(), "sign", s.index, { ...item, facing: normAngle(item.facing + 45) }));
  }

  function deleteSelected() {
    const s = selected();
    if (!s || !selItem()) return;
    const words = { wall: "Wall deleted.", door: "Door deleted.", label: "Room name deleted.", sign: "Sign taken off the plan." };
    // A focused sign is about to disappear; keep keyboard focus on the plan.
    const refocus = svg?.contains(document.activeElement) && document.activeElement !== svg;
    commit(withoutItem(plan(), s.kind, s.index));
    setSelected(null);
    if (refocus) svg.focus({ preventScroll: true });
    setNotice(words[s.kind] + " Undo brings it back.");
  }

  function onCanvasKey(e) {
    const keys = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (keys[e.key]) {
      e.preventDefault();
      const [x, y] = keys[e.key];
      if (selItem()) {
        const step = e.shiftKey ? 0.1 : GRID;
        moveSelected(x * step, y * step);
      } else {
        const v = view();
        setView({ ...v, cx: v.cx + x, cy: v.cy + y });
      }
      return;
    }
    if ((e.key === "Delete" || e.key === "Backspace") && selItem()) {
      e.preventDefault();
      deleteSelected();
      return;
    }
    if ((e.key === "r" || e.key === "R") && !e.ctrlKey && !e.metaKey && selItem()) {
      e.preventDefault();
      rotateSelected();
      return;
    }
    if (e.key === "Escape") {
      if (action) cancelAction();
      setSelected(null);
      return;
    }
    if (e.key === "+" || e.key === "=") zoomBy(1.25);
    if (e.key === "-" || e.key === "_") zoomBy(0.8);
  }

  function onRootKey(e) {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === "z" || e.key === "Z") && !isTyping(e.target)) {
      e.preventDefault();
      undo();
    }
  }

  // Plan size
  function setDimension(key, value) {
    const v = Number(value);
    const next = round2(clamp(v, PLAN_LIMITS.min, PLAN_LIMITS.max));
    if (value !== "" && Number.isFinite(v) && next !== plan()[key]) {
      commit({ ...plan(), [key]: next });
      fit();
    }
    // Show what the plan really uses, such as 50 after typing 80.
    setWidthText(String(plan().width));
    setHeightText(String(plan().height));
  }

  // Label text: one undo step per edit, not per key.
  let labelBefore = null;
  function onLabelInput(text) {
    const s = selected();
    if (!s || s.kind !== "label") return;
    if (!labelBefore) labelBefore = plan();
    setPlan(withItem(plan(), "label", s.index, { ...selItem(), text }));
  }
  function onLabelDone() {
    if (labelBefore && labelBefore !== plan()) setUndoStack((stack) => [...stack.slice(-(UNDO_LIMIT - 1)), labelBefore]);
    labelBefore = null;
  }

  async function save() {
    if (!dirty() || saving()) return;
    setSaving(true);
    setNotice("");
    setError("");
    const toSend = { ...plan(), labels: plan().labels.filter((l) => l.text.trim()).map((l) => ({ ...l, text: l.text.trim() })) };
    try {
      const result = await savePlan(toSend);
      const next = normalizePlan(result && typeof result === "object" ? result : toSend);
      batch(() => {
        setPlan(next);
        setSavedJson(JSON.stringify(next));
      });
      props.onSaved?.(next);
      setNotice("Plan saved.");
    } catch (err) {
      setError(`Couldn't save the plan. ${err.message}`);
    } finally {
      setSaving(false);
    }
  }

  // Drawing helpers
  const grid = createMemo(() => {
    const { width: W, height: H } = plan();
    let minor = "";
    let major = "";
    for (let i = 0; i * GRID <= W + 1e-9; i++) {
      const s = `M${i * GRID} 0V${H}`;
      if (i % 2 === 0) major += s;
      else minor += s;
    }
    for (let i = 0; i * GRID <= H + 1e-9; i++) {
      const s = `M0 ${i * GRID}H${W}`;
      if (i % 2 === 0) major += s;
      else minor += s;
    }
    return { minor, major };
  });

  const arrows = createMemo(() => {
    const pos = new Map(plan().signs.filter((s) => signById().has(s.sign)).map((s) => [s.sign, s]));
    const pairs = routePairs(props.guide);
    const r = iconSize() * 0.8;
    const head = px(9);
    const out = [];
    for (const link of props.links || []) {
      const a = pos.get(link.from);
      const b = pos.get(link.to);
      if (!a || !b || link.from === link.to) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const len = Math.hypot(dx, dy);
      if (len < 2 * r + 0.05) continue;
      const ux = dx / len;
      const uy = dy / len;
      const sx = a.x + ux * r;
      const sy = a.y + uy * r;
      const ex = b.x - ux * r;
      const ey = b.y - uy * r;
      // Bend to the left of travel, so the two directions between a pair don't overlap.
      const bend = len * 0.16;
      const qx = (sx + ex) / 2 + uy * bend;
      const qy = (sy + ey) / 2 - ux * bend;
      const tx = ex - qx;
      const ty = ey - qy;
      const tl = Math.hypot(tx, ty) || 1;
      const hx = tx / tl;
      const hy = ty / tl;
      const p1 = `${ex - hx * head + hy * head * 0.55} ${ey - hy * head - hx * head * 0.55}`;
      const p2 = `${ex - hx * head - hy * head * 0.55} ${ey - hy * head + hx * head * 0.55}`;
      out.push({
        key: `${link.from}>${link.to}`,
        d: `M${sx} ${sy}Q${qx} ${qy} ${ex} ${ey}`,
        head: `M${ex} ${ey}L${p1}L${p2}Z`,
        on: pairs.has(`${link.from}>${link.to}`),
      });
    }
    return out.sort((x, y) => Number(x.on) - Number(y.on));
  });

  const scaleBar = () => {
    const m = niceLength(view().scale);
    return { m, px: Math.round(m * view().scale) };
  };

  const isSel = (kind, index) => selected()?.kind === kind && selected()?.index === index;

  const summary = () => {
    const p = plan();
    const parts = [
      `${formatMetres(p.width)} by ${formatMetres(p.height)} plan`,
      count(p.walls.length, "wall"),
      count(p.doors.length, "door"),
      count(p.labels.length, "room name"),
      count(p.signs.length, "sign"),
    ];
    return parts.join(", ") + ".";
  };

  const selectionTitle = () => {
    const s = selected();
    const item = selItem();
    if (!s || !item) return "";
    if (s.kind === "wall") return `Wall, ${formatMetres(Math.hypot(item.x2 - item.x1, item.y2 - item.y1))} long`;
    if (s.kind === "door") return "Door";
    if (s.kind === "label") return "Room name";
    return `Sign: ${signName(signById().get(item.sign), item.sign)}`;
  };

  const [widthText, setWidthText] = createSignal("");
  const [heightText, setHeightText] = createSignal("");
  createEffect(() => {
    setWidthText(String(plan().width));
    setHeightText(String(plan().height));
  });

  return (
    <section class="plan-editor" aria-labelledby="plan-heading" onKeyDown={onRootKey}>
      <div class="plan-head">
        <div>
          <h2 id="plan-heading">Floor plan</h2>
          <p class="muted">
            Draw the walls and doors, then place each sign. The shaded wedge in front of a sign is where they can stand
            for the camera to read it.
          </p>
        </div>
      </div>

      <div class="plan-bar">
        <div class="plan-tools" role="group" aria-label="Drawing tools">
          <For each={TOOLS}>
            {(t) => (
              <button
                type="button"
                class="tool"
                aria-pressed={tool() === t.id}
                disabled={t.id === "sign" && !(props.signs || []).length}
                title={t.id === "sign" && !(props.signs || []).length ? "Add a sign first" : undefined}
                onClick={() => chooseTool(t.id)}
              >
                <t.Icon />
                <span>{t.label}</span>
              </button>
            )}
          </For>
        </div>
        <div class="plan-actions">
          <button type="button" class="tool" title="Undo" disabled={!undoStack().length} onClick={undo}>
            <UndoIcon />
            <span class="tool-label-optional">Undo</span>
          </button>
          <span class="plan-zoom" role="group" aria-label="Zoom">
            <button type="button" class="tool icon-only" aria-label="Zoom out" title="Zoom out" onClick={() => zoomBy(0.8)}>
              <ZoomOutIcon />
            </button>
            <button type="button" class="tool icon-only" aria-label="Zoom in" title="Zoom in" onClick={() => zoomBy(1.25)}>
              <ZoomInIcon />
            </button>
            <button type="button" class="tool" title="Zoom to fit the whole plan" onClick={fit}>
              <FitIcon />
              <span class="tool-label-optional">Fit</span>
            </button>
          </span>
          <button type="button" class="button primary plan-save" disabled={!dirty() || saving() || offline()} onClick={save}>
            {saving() ? "Saving…" : "Save plan"}
          </button>
        </div>
      </div>

      <Show when={tool() === "sign" && (props.signs || []).length}>
        <div class="plan-option">
          <label for="plan-sign">Sign to place</label>
          <select id="plan-sign" value={armed() ?? ""} onChange={(e) => setArmed(Number(e.currentTarget.value))}>
            <For each={props.signs}>
              {(s) => (
                <option value={s.id} selected={armed() === s.id}>
                  {signName(s)}
                  {placedIds().has(s.id) ? " (on the plan)" : ""}
                </option>
              )}
            </For>
          </select>
        </div>
      </Show>

      <Show when={selItem()}>
        <div class="plan-selection" role="group" aria-label="Selected item">
          <p class="plan-selection-title">{selectionTitle()}</p>
          <Show when={selected()?.kind === "label"}>
            <label class="sr-only" for="plan-label-text">
              Room name
            </label>
            <input
              ref={labelInput}
              id="plan-label-text"
              class="plan-input"
              maxlength="40"
              autocomplete="off"
              value={selItem()?.text ?? ""}
              onInput={(e) => onLabelInput(e.currentTarget.value)}
              onChange={onLabelDone}
              onBlur={onLabelDone}
            />
          </Show>
          <Show when={selected()?.kind === "door"}>
            <label class="plan-inline">
              <span>Width</span>
              <select
                value={String(selItem()?.width)}
                onChange={(e) => commit(withItem(plan(), "door", selected().index, { ...selItem(), width: Number(e.currentTarget.value) }))}
              >
                <Show when={!DOOR_WIDTHS.includes(selItem()?.width)}>
                  <option value={String(selItem()?.width)} selected>
                    {formatMetres(selItem()?.width)}
                  </option>
                </Show>
                <For each={DOOR_WIDTHS}>
                  {(w) => (
                    <option value={String(w)} selected={selItem()?.width === w}>
                      {formatMetres(w)}
                    </option>
                  )}
                </For>
              </select>
            </label>
          </Show>
          <Show when={selected()?.kind === "sign"}>
            <a class="text-link" href={`/home/signs/${selItem()?.sign}`}>
              Open sign
            </a>
          </Show>
          <div class="actions">
            <Show when={selected()?.kind === "door" || selected()?.kind === "sign"}>
              <button type="button" class="tool" onClick={rotateSelected}>
                <RotateIcon />
                <span>Rotate</span>
              </button>
            </Show>
            <button type="button" class="tool tool-danger" onClick={deleteSelected}>
              {selected()?.kind === "sign" ? "Take off plan" : "Delete"}
            </button>
          </div>
        </div>
      </Show>

      <div class="plan-canvas" classList={{ [`tool-${tool()}`]: true }}>
        <svg
          ref={svg}
          class="plan-svg"
          viewBox={viewBox()}
          tabindex="0"
          role="application"
          aria-roledescription="floor plan editor"
          aria-label="Floor plan"
          aria-describedby="plan-summary plan-keys"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onLostPointerCapture={(e) => pointers.has(e.pointerId) && onPointerUp(e)}
          onKeyDown={onCanvasKey}
        >
          <rect class="plan-floor" x="0" y="0" width={plan().width} height={plan().height} />
          <path class="plan-grid-minor" d={grid().minor} vector-effect="non-scaling-stroke" />
          <path class="plan-grid-major" d={grid().major} vector-effect="non-scaling-stroke" />
          <rect class="plan-edge" x="0" y="0" width={plan().width} height={plan().height} vector-effect="non-scaling-stroke" />

          {/* Reading zones sit under everything else. */}
          <Index each={plan().signs}>
            {(s) => (
              <Show when={signById().has(s().sign)}>
                <path class="plan-zone" d={wedge(s().x, s().y, s().facing)} vector-effect="non-scaling-stroke" />
              </Show>
            )}
          </Index>

          <For each={arrows()}>
            {(a) => (
              <g class="plan-link" classList={{ "is-route": a.on }}>
                <path class="plan-link-line" d={a.d} vector-effect="non-scaling-stroke" />
                <path class="plan-link-head" d={a.head} />
              </g>
            )}
          </For>

          <Index each={plan().walls}>
            {(w, i) => (
              <g data-kind="wall" data-index={i} class="plan-wall" classList={{ "is-selected": isSel("wall", i) }}>
                <line class="hit" x1={w().x1} y1={w().y1} x2={w().x2} y2={w().y2} vector-effect="non-scaling-stroke" />
                <line class="wall-line" x1={w().x1} y1={w().y1} x2={w().x2} y2={w().y2} vector-effect="non-scaling-stroke" />
              </g>
            )}
          </Index>

          <Index each={plan().doors}>
            {(d, i) => {
              const half = () => d().width / 2;
              return (
                <g
                  data-kind="door"
                  data-index={i}
                  class="plan-door"
                  classList={{ "is-selected": isSel("door", i) }}
                  transform={`translate(${d().x} ${d().y}) rotate(${d().angle})`}
                >
                  <rect class="hit" x={-half()} y={-0.2} width={d().width} height={d().width + 0.2} />
                  <line class="door-gap" x1={-half()} y1="0" x2={half()} y2="0" vector-effect="non-scaling-stroke" />
                  <path
                    class="door-swing"
                    d={`M${-half()} ${d().width}A${d().width} ${d().width} 0 0 0 ${half()} 0`}
                    vector-effect="non-scaling-stroke"
                  />
                  <line class="door-leaf" x1={-half()} y1="0" x2={-half()} y2={d().width} vector-effect="non-scaling-stroke" />
                </g>
              );
            }}
          </Index>

          <Index each={plan().labels}>
            {(l, i) => (
              <text
                data-kind="label"
                data-index={i}
                class="plan-label"
                classList={{ "is-selected": isSel("label", i), "is-empty": !l().text.trim() }}
                x={l().x}
                y={l().y}
                font-size={labelSize()}
              >
                {l().text.trim() || "Room name"}
              </text>
            )}
          </Index>

          <Index each={plan().signs}>
            {(s, i) => {
              const info = () => signById().get(s().sign);
              const name = () => signName(info(), s().sign);
              const nameSpot = () => {
                const f = rad(s().facing);
                const fx = Math.cos(f);
                const fy = Math.sin(f);
                const gap = iconSize() / 2 + px(6);
                if (Math.abs(fx) > Math.abs(fy)) {
                  return { x: s().x + Math.sign(fx) * gap, y: s().y + iconSize() / 2 + textSize(), anchor: fx > 0 ? "start" : "end" };
                }
                return { x: s().x, y: s().y + fy * (gap + textSize() * 0.75) + textSize() * 0.35, anchor: "middle" };
              };
              return (
                <Show when={info()}>
                  <g
                    data-kind="sign"
                    data-index={i}
                    class="plan-sign"
                    classList={{
                      "is-selected": isSel("sign", i),
                      "is-room": props.room?.id === s().sign,
                      "is-in-view": !!props.inView?.has(s().sign),
                    }}
                    tabindex="0"
                    role="button"
                    aria-label={`${name()} sign${props.room?.id === s().sign ? ", where they are now" : ""}`}
                    onFocus={() => setSelected({ kind: "sign", index: i })}
                  >
                    <Show when={props.room?.id === s().sign}>
                      <circle class="room-ring" cx={s().x} cy={s().y} r={iconSize() * 0.95} vector-effect="non-scaling-stroke" />
                    </Show>
                    <circle class="sign-halo" cx={s().x} cy={s().y} r={iconSize() * 0.78} vector-effect="non-scaling-stroke" />
                    <Marker id={s().sign} size={iconSize()} quiet={0.6} x={s().x - iconSize() / 2} y={s().y - iconSize() / 2} />
                    <text class="sign-name" x={nameSpot().x} y={nameSpot().y} text-anchor={nameSpot().anchor} font-size={textSize()}>
                      {name()}
                    </text>
                  </g>
                </Show>
              );
            }}
          </Index>

          {/* Endpoint handles for the selected wall. */}
          <Show when={selected()?.kind === "wall" && selItem()}>
            <circle
              data-kind="wall"
              data-index={selected().index}
              data-handle="1"
              class="plan-handle"
              cx={selItem().x1}
              cy={selItem().y1}
              r={px(9)}
              vector-effect="non-scaling-stroke"
            />
            <circle
              data-kind="wall"
              data-index={selected().index}
              data-handle="2"
              class="plan-handle"
              cx={selItem().x2}
              cy={selItem().y2}
              r={px(9)}
              vector-effect="non-scaling-stroke"
            />
          </Show>

          <Show when={draft()}>
            <line
              class="wall-draft"
              x1={draft().x1}
              y1={draft().y1}
              x2={draft().x2}
              y2={draft().y2}
              vector-effect="non-scaling-stroke"
            />
            <text class="draft-length" x={draft().x2 + px(10)} y={draft().y2 - px(10)} font-size={textSize()}>
              {formatMetres(Math.hypot(draft().x2 - draft().x1, draft().y2 - draft().y1))}
            </text>
          </Show>
        </svg>

        <div class="plan-scale" aria-hidden="true">
          <span class="plan-scale-bar" style={{ width: `${scaleBar().px}px` }} />
          <span>{formatMetres(scaleBar().m)}</span>
        </div>

        <Show when={loaded() && !plan().walls.length && tool() !== "wall"}>
          <p class="plan-empty">
            Start with the walls: choose <strong>Wall</strong>, then press and drag.
          </p>
        </Show>
      </div>

      <p id="plan-summary" class="sr-only">
        {summary()}
      </p>
      <p id="plan-keys" class="sr-only">
        Select an item, then use the arrow keys to move it, R to rotate it, and Delete to remove it. Without a selection,
        the arrow keys move the view. Plus and minus zoom.
      </p>

      <div class="plan-foot">
        <div class="plan-size" role="group" aria-label="Plan size in metres">
          <label for="plan-width">Width</label>
          <input
            id="plan-width"
            class="plan-input plan-number"
            type="number"
            inputmode="decimal"
            min={PLAN_LIMITS.min}
            max={PLAN_LIMITS.max}
            step="0.5"
            value={widthText()}
            onInput={(e) => setWidthText(e.currentTarget.value)}
            onChange={(e) => setDimension("width", e.currentTarget.value)}
          />
          <span aria-hidden="true">×</span>
          <label for="plan-height">Height</label>
          <input
            id="plan-height"
            class="plan-input plan-number"
            type="number"
            inputmode="decimal"
            min={PLAN_LIMITS.min}
            max={PLAN_LIMITS.max}
            step="0.5"
            value={heightText()}
            onInput={(e) => setHeightText(e.currentTarget.value)}
            onChange={(e) => setDimension("height", e.currentTarget.value)}
          />
          <span class="muted">metres</span>
        </div>
        <p class="plan-hint muted">
          {HINTS[tool()]}
          <span class="touch-hint"> Two fingers move and zoom the plan.</span>
        </p>
        <p role="status" class="ok-text plan-notice">
          {notice()}
        </p>
        <Show when={dirty()}>
          <p class="plan-unsaved">Changes not saved yet.</p>
        </Show>
        <p role="alert" class="error-text">
          {error()}
        </p>
      </div>
    </section>
  );
}

function formatMetres(m) {
  if (!Number.isFinite(m)) return "";
  const r = Math.round(m * 10) / 10;
  return `${Number.isInteger(r) ? r : r.toFixed(1)} m`;
}

function count(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

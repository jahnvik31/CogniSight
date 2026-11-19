// Shared helpers for signs, directions, and the floor plan. No network calls live here.
import { ago } from "./lib";

// After this long without reading a sign, "In the hallway" becomes "Last seen in the hallway".
export const ROOM_FRESH_SECONDS = 120;

export const PLAN_LIMITS = { min: 2, max: 50, walls: 400, doors: 100, labels: 60 };

const num = (v, fallback = 0) => (typeof v === "number" && Number.isFinite(v) ? v : fallback);
export const round2 = (v) => Math.round(v * 100) / 100;

export function signsOf(home) {
  return Array.isArray(home?.signs) ? home.signs.filter((s) => s && Number.isInteger(s.id)) : [];
}

export function linksOf(home) {
  return Array.isArray(home?.links)
    ? home.links.filter((l) => l && Number.isInteger(l.from) && Number.isInteger(l.to))
    : [];
}

export function signName(sign, id) {
  return sign?.name || `Sign ${id ?? sign?.id ?? ""}`.trim();
}

// "the hallway" for "Hallway", but "Priya's room" stays as it is. Lower-cases the
// first letter only when the next one is lower case, so "TV room" keeps its capitals.
export function placeName(name) {
  const text = (name || "").trim();
  if (!text) return "this room";
  if (/^the\s/i.test(text)) return "the " + text.slice(4);
  if (/^\S+['’]s(\s|$)/i.test(text) || /^(my|your)\s/i.test(text)) return text;
  const lowered = /^[A-Z][a-z]/.test(text) ? text.charAt(0).toLowerCase() + text.slice(1) : text;
  return "the " + lowered;
}

export function arrivalSentence(name) {
  return `This is ${placeName(name)}.`;
}

// The room line used on Live: "In the hallway" or "Last seen in the hallway, 4 min ago".
export function roomLine(room, now) {
  if (!room || !room.name) return null;
  const seen = num(room.seen_at, NaN);
  if (Number.isFinite(seen) && now - seen > ROOM_FRESH_SECONDS) {
    return { text: `Last seen in ${placeName(room.name)}, ${ago(seen, now)}`, stale: true };
  }
  return { text: `In ${placeName(room.name)}`, stale: false };
}

// "toilet, washroom" → ["toilet", "washroom"]
export function splitNames(text) {
  return (text || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function emptyPlan() {
  return { width: 12, height: 9, walls: [], doors: [], labels: [], signs: [] };
}

// Makes whatever the device sent safe to draw: finite numbers, arrays present.
export function normalizePlan(plan) {
  if (!plan || typeof plan !== "object") return emptyPlan();
  const clampSize = (v, d) => Math.min(PLAN_LIMITS.max, Math.max(PLAN_LIMITS.min, num(v, d)));
  const list = (v) => (Array.isArray(v) ? v.filter((x) => x && typeof x === "object") : []);
  return {
    width: clampSize(plan.width, 12),
    height: clampSize(plan.height, 9),
    walls: list(plan.walls)
      .map((w) => ({ x1: num(w.x1), y1: num(w.y1), x2: num(w.x2), y2: num(w.y2) }))
      .filter((w) => w.x1 !== w.x2 || w.y1 !== w.y2),
    doors: list(plan.doors).map((d) => ({ x: num(d.x), y: num(d.y), angle: num(d.angle), width: num(d.width, 0.9) || 0.9 })),
    labels: list(plan.labels).map((l) => ({ x: num(l.x), y: num(l.y), text: typeof l.text === "string" ? l.text : "" })),
    signs: list(plan.signs)
      .filter((s) => Number.isInteger(s.sign))
      .map((s) => ({ sign: s.sign, x: num(s.x), y: num(s.y), facing: num(s.facing, 90) })),
  };
}

// Pairs of sign ids along a guide's route, as "from>to" keys.
export function routePairs(guide) {
  const route = Array.isArray(guide?.route) ? guide.route : [];
  const pairs = new Set();
  for (let i = 1; i < route.length; i++) pairs.add(`${route[i - 1]}>${route[i]}`);
  return pairs;
}

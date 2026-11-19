// Small shared helpers: polling, clocks, and wording. No network calls live here.
import { createEffect, createSignal, onCleanup } from "solid-js";
import { deviceNow } from "./api";

// True while the page is on screen. Polling and the camera stream pause otherwise.
export function usePageVisible() {
  const [visible, setVisible] = createSignal(!document.hidden);
  const update = () => setVisible(!document.hidden);
  document.addEventListener("visibilitychange", update);
  onCleanup(() => document.removeEventListener("visibilitychange", update));
  return visible;
}

// Calls `fetcher` every `interval` ms while the page is visible. Never overlaps
// requests. Keeps the last good data when a request fails.
export function usePoll(fetcher, interval) {
  const [data, setData] = createSignal(undefined);
  const [error, setError] = createSignal(null);
  let timer;
  let stopped = false;
  let inflight = false;
  let again = false;

  async function tick() {
    clearTimeout(timer);
    if (stopped) return;
    if (inflight) {
      again = true;
      return;
    }
    if (document.hidden) return;
    inflight = true;
    try {
      const value = await fetcher();
      if (!stopped) {
        setData(() => value);
        setError(null);
      }
    } catch (err) {
      if (!stopped) setError(() => err);
    } finally {
      inflight = false;
    }
    if (stopped) return;
    if (again) {
      again = false;
      tick();
      return;
    }
    if (!document.hidden) timer = setTimeout(tick, interval);
  }

  const onVisibility = () => {
    if (document.hidden) clearTimeout(timer);
    else tick();
  };
  document.addEventListener("visibilitychange", onVisibility);
  tick();
  onCleanup(() => {
    stopped = true;
    clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVisibility);
  });

  return {
    data,
    error,
    refresh: tick,
    mutate: (value) => setData(() => value),
    loaded: () => data() !== undefined,
  };
}

// The device's current time in seconds, updated every `ms`.
export function useNow(ms = 1000) {
  const [now, setNow] = createSignal(deviceNow());
  const id = setInterval(() => setNow(deviceNow()), ms);
  onCleanup(() => clearInterval(id));
  return now;
}

export function useTitle(title) {
  createEffect(() => {
    const value = typeof title === "function" ? title() : title;
    document.title = value ? `${value} – CogniSight` : "CogniSight";
  });
}

export function plural(count, one, many = one + "s") {
  return `${count} ${count === 1 ? one : many}`;
}

export function ago(at, now) {
  if (typeof at !== "number" || !Number.isFinite(at)) return "";
  const s = Math.max(0, now - at);
  if (s < 10) return "just now";
  if (s < 60) return `${Math.floor(s / 10) * 10} sec ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} hr ago`;
  if (s < 172800) return "yesterday";
  return `${Math.floor(s / 86400)} days ago`;
}

// Device epoch seconds to a Date on this browser's clock.
export function toLocalDate(at) {
  return new Date((at - (deviceNow() - Date.now() / 1000)) * 1000);
}

export function isoTime(at) {
  try {
    return new Date(at * 1000).toISOString();
  } catch {
    return undefined;
  }
}

export function clockTime(at) {
  try {
    return toLocalDate(at).toLocaleString(undefined, {
      weekday: "short",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function duration(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "Unknown";
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return plural(s, "second");
  const m = Math.floor(s / 60);
  if (m < 60) return plural(m, "minute");
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hr ${m % 60} min`;
  const d = Math.floor(h / 24);
  return `${plural(d, "day")} ${h % 24} hr`;
}

export function capitalise(text) {
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function safeDecode(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export function personHref(name) {
  return "/people/" + encodeURIComponent(name);
}

// Shrinks large phone photos before upload so the Pi spends less time on them.
// Falls back to the original file if the browser can't decode it.
export async function prepareImage(file, max = 1600) {
  if (!file || typeof createImageBitmap !== "function") return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size < 2_500_000 && /jpe?g|png|webp/i.test(file.type)) {
      bitmap.close?.();
      return file;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    if (!blob) return file;
    const base = (file.name || "photo").replace(/\.[^.]+$/, "");
    return new File([blob], `${base}.jpg`, { type: "image/jpeg" });
  } catch {
    return file;
  }
}

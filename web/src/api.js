// Every request to the device goes through this file. The contract is docs/API.md.
import { createSignal } from "solid-js";

export const STREAM_URL = "/stream.mjpg";

const UNREACHABLE = "Can't reach the device. Check that it is switched on and on the same Wi-Fi as this phone or computer.";

// True while the device does not answer at all. Drives the one banner in the layout.
const [offline, setOffline] = createSignal(false);
export { offline };

// Seconds to add to this browser's clock to get the device's clock. Read from the
// HTTP Date header so "2 min ago" stays right when the phone's clock is off.
let skew = 0;
export function deviceNow() {
  return Date.now() / 1000 + skew;
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function fallbackMessage(status) {
  if (status === 404) return "That wasn't found on the device. It may have just been deleted. Reload the page to see the latest.";
  if (status === 413) return "That photo is too large for the device. Try a smaller one.";
  if (status >= 500) return `The device ran into a problem (error ${status}). Try again in a moment.`;
  return `The device couldn't do that (error ${status}).`;
}

async function request(path, { method = "GET", json, form, timeout = 10000 } = {}) {
  const init = { method, headers: { Accept: "application/json" } };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  } else if (form) {
    init.body = form;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  init.signal = controller.signal;

  let response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    clearTimeout(timer);
    if (err?.name === "AbortError" && method !== "GET") {
      throw new ApiError("The device took too long to answer. Check the Live page, then try again.", 0);
    }
    setOffline(true);
    throw new ApiError(UNREACHABLE, 0);
  }

  let text = "";
  try {
    text = await response.text();
  } catch {
    clearTimeout(timer);
    setOffline(true);
    throw new ApiError(UNREACHABLE, 0);
  }
  clearTimeout(timer);

  const date = Date.parse(response.headers.get("Date") || "");
  if (!Number.isNaN(date)) {
    const measured = (date - Date.now()) / 1000;
    // The header only has whole seconds, so ignore differences that small.
    skew = Math.abs(measured) > 2 ? measured : 0;
  }

  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (response.ok) {
    if (response.status === 204) {
      setOffline(false);
      return null;
    }
    if (data === null || typeof data !== "object") {
      setOffline(false);
      throw new ApiError("The device sent a reply this page doesn't understand. Make sure the dashboard and the device software are the same version.", response.status);
    }
    setOffline(false);
    return data;
  }

  if (data && typeof data.error === "string" && data.error) {
    setOffline(false);
    throw new ApiError(data.error, response.status);
  }
  // A proxy or gateway answered for a device that is down.
  if (response.status === 502 || response.status === 504 || (response.status >= 500 && data === null)) {
    setOffline(true);
    throw new ApiError(UNREACHABLE, response.status);
  }
  setOffline(false);
  throw new ApiError(fallbackMessage(response.status), response.status);
}

const enc = encodeURIComponent;
const personPath = (name) => "/api/people/" + enc(name);

// Live
export const getLive = () => request("/api/live");
export const getEvents = (limit = 50) =>
  request("/api/events?limit=" + enc(limit)).then((data) => (Array.isArray(data.events) ? data.events : []));

// Device
export const getStatus = () => request("/api/status");
export const setSpeech = (enabled) => request("/api/speech", { method: "POST", json: { enabled } });
export const testSpeech = (text) =>
  request("/api/speech/test", { method: "POST", json: text ? { text } : {}, timeout: 20000 });
export const setListening = (enabled) => request("/api/listening", { method: "POST", json: { enabled } });

// People
export const listPeople = () =>
  request("/api/people").then((data) => (Array.isArray(data.people) ? data.people : []));

export function addPerson({ name, relationship, note, photo }) {
  const form = new FormData();
  form.set("name", name);
  if (relationship) form.set("relationship", relationship);
  if (note) form.set("note", note);
  if (photo) form.set("photo", photo, photo.name || "photo.jpg");
  // Capturing and checking for a face can take a while on the Pi.
  return request("/api/people", { method: "POST", form, timeout: 60000 });
}

export const updatePerson = (name, fields) => request(personPath(name), { method: "PATCH", json: fields });
export const deletePerson = (name) => request(personPath(name), { method: "DELETE" });

export function addPhoto(name, photo) {
  const form = new FormData();
  if (photo) form.set("photo", photo, photo.name || "photo.jpg");
  return request(personPath(name) + "/photos", { method: "POST", form, timeout: 60000 });
}

export const deletePhoto = (name, filename) =>
  request(personPath(name) + "/photos/" + enc(filename), { method: "DELETE" });

export const photoUrl = (name, filename) => personPath(name) + "/photos/" + enc(filename);

// Location
export const getLocation = () => request("/api/location", { timeout: 20000 });
export const refreshLocation = () => request("/api/location/refresh", { method: "POST", timeout: 30000 });

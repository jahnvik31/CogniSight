import { createEffect, createSignal, on, onCleanup, Show } from "solid-js";
import { offline, STREAM_URL } from "./api";
import { usePageVisible } from "./lib";

// The live MJPEG stream in a rounded frame. The device draws boxes and names on it.
// props.camera: the device's own view of whether the camera runs (true/false), or
// undefined when unknown. props.frame: {width, height} for the aspect ratio.
// props.children: overlays such as the subtitle strip.
export default function Camera(props) {
  const visible = usePageVisible();
  const [key, setKey] = createSignal(Date.now());
  // loading: waiting for the first frame. ok: frames arriving. error: the stream failed.
  const [state, setState] = createSignal("loading");
  let img;

  const reconnect = () => {
    setKey(Date.now());
    if (state() === "ok") setState("loading");
  };

  // Keep retrying every 5 s while the stream is failing.
  createEffect(() => {
    if (state() !== "error") return;
    const id = setInterval(() => setKey(Date.now()), 5000);
    onCleanup(() => clearInterval(id));
  });

  // Some browsers never fire `load` for MJPEG, so also look for a decoded frame.
  const check = setInterval(() => {
    if (state() !== "ok" && img && img.naturalWidth > 0 && img.complete !== false) setState("ok");
  }, 1000);
  onCleanup(() => clearInterval(check));

  // Reconnect when the camera comes back, the device becomes reachable, or the tab returns.
  createEffect(on(() => props.camera, (cam, prev) => cam === true && prev === false && reconnect(), { defer: true }));
  createEffect(on(offline, (down, prev) => !down && prev && reconnect(), { defer: true }));
  createEffect(on(visible, (shown) => shown && reconnect(), { defer: true }));

  const ratio = () => {
    const f = props.frame;
    return f && f.width > 0 && f.height > 0 ? `${f.width} / ${f.height}` : "4 / 3";
  };

  const problem = () => {
    if (offline()) return "offline";
    if (props.camera === false || state() === "error") return "camera";
    if (state() === "loading") return "loading";
    return null;
  };

  return (
    <div class="stage" classList={{ compact: !!props.compact }}>
      <div class="frame" style={{ "aspect-ratio": ratio() }}>
        <Show when={visible()}>
          <img
            ref={img}
            class="stream"
            classList={{ hidden: problem() !== null }}
            src={`${STREAM_URL}?t=${key()}`}
            alt={props.alt || "Live view from the device camera, with names drawn around recognised faces"}
            onLoad={() => setState("ok")}
            onError={() => setState("error")}
          />
        </Show>
        <Show when={problem() === null}>
          <span class="live-chip">
            <span class="pulse" aria-hidden="true" />
            Live
          </span>
        </Show>
        <Show when={problem()}>
          <div class="frame-message" role={problem() === "loading" ? undefined : "status"}>
            <Show when={problem() === "loading"}>
              <p class="frame-title">Connecting to the camera…</p>
            </Show>
            <Show when={problem() === "offline"}>
              <p class="frame-title">Waiting for the device</p>
              <p>The picture comes back on its own when the device can be reached again.</p>
            </Show>
            <Show when={problem() === "camera"}>
              <p class="frame-title">The camera isn't running.</p>
              <p>Check the ribbon cable and restart CogniSight.</p>
              <p class="frame-retry">Trying again every 5 seconds.</p>
            </Show>
          </div>
        </Show>
      </div>
      {props.children}
    </div>
  );
}

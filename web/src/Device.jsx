import { createSignal, For, Show } from "solid-js";
import { offline, setListening, setSpeech } from "./api";
import { useStatus } from "./context";
import { ago, duration, plural, useNow, useTitle } from "./lib";

function Card(props) {
  return (
    <section class={`status-card tone-${props.tone}`} aria-labelledby={props.id}>
      <h2 id={props.id} class="h3">
        {props.title}
      </h2>
      <p class="status-word">
        <span class="dot" aria-hidden="true" />
        {props.state}
      </p>
      {props.children}
    </section>
  );
}

function Toggle(props) {
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  async function run() {
    setBusy(true);
    setError("");
    try {
      await props.onToggle(!props.enabled);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button type="button" class="button" disabled={busy() || !props.available || offline()} onClick={run}>
        {busy() ? "Changing…" : props.enabled ? props.offLabel : props.onLabel}
      </button>
      <p role="alert" class="error-text">
        {error()}
      </p>
    </>
  );
}

function heardText(heard, now) {
  if (!heard) return "Nothing yet";
  if (typeof heard === "string") return `“${heard}”`;
  if (typeof heard === "object" && heard.text) {
    return `“${heard.text}”${Number.isFinite(heard.at) ? `, ${ago(heard.at, now)}` : ""}`;
  }
  return "Nothing yet";
}

export default function Device() {
  useTitle("Device");
  const status = useStatus();
  const now = useNow(5000);
  const s = () => status.data();

  const problems = () => {
    const d = s();
    if (!d) return [];
    const list = [];
    if (!d.camera?.ok) list.push("the camera");
    if (!d.recognition?.ok) list.push("recognition");
    if (d.speech && !d.speech.available) list.push("speech");
    return list;
  };

  const summary = () => {
    const p = problems();
    if (p.length === 0) return "Everything CogniSight needs is running.";
    const joined = p.length === 1 ? p[0] : `${p.slice(0, -1).join(", ")} and ${p[p.length - 1]}`;
    return `Needs attention: ${joined}.`;
  };

  async function toggleSpeech(enabled) {
    const next = await setSpeech(enabled);
    if (next && typeof next === "object") status.mutate({ ...s(), speech: next });
    status.refresh();
  }

  async function toggleListening(enabled) {
    const next = await setListening(enabled);
    if (next && typeof next === "object") status.mutate({ ...s(), listening: next });
    status.refresh();
  }

  const fixed = (v, digits) => (Number.isFinite(v) ? v.toFixed(digits) : "Unknown");

  return (
    <div class="page device">
      <div class="page-head">
        <h1 tabindex="-1">Device</h1>
        <Show
          when={s()}
          fallback={<p class="lede">{offline() ? "Waiting for the device." : "Checking the device…"}</p>}
        >
          <p class="lede" classList={{ "lede-attention": problems().length > 0 }}>
            {summary()}
          </p>
        </Show>
      </div>

      <Show when={status.error() && !s() && !offline()}>
        <p class="error-text" role="alert">
          Couldn't read the device status. {status.error().message}
        </p>
      </Show>

      <Show when={s()}>
        <Show when={s().urls?.length}>
          <section class="open-on-phone" aria-labelledby="urls-heading">
            <h2 id="urls-heading" class="h3">
              Open this dashboard on a phone
            </h2>
            <p class="muted">Connect the phone to the same Wi-Fi as the device, then go to:</p>
            <ul class="urls" role="list">
              <For each={s().urls}>
                {(url) => (
                  <li>
                    <a href={url}>{url.replace(/^https?:\/\//, "")}</a>
                  </li>
                )}
              </For>
            </ul>
          </section>
        </Show>

        <div class="status-grid">
          <Card
            id="card-camera"
            title="Camera"
            tone={s().camera?.ok ? "ok" : "attention"}
            state={s().camera?.ok ? "Running" : "Not running"}
          >
            <Show when={s().camera?.label || s().camera?.kind}>
              <p class="muted">
                {[s().camera?.label, s().camera?.kind].filter(Boolean).join(" using ")}
              </p>
            </Show>
            <Show when={s().camera?.error}>
              <p class="card-error">{s().camera.error}</p>
            </Show>
            <Show when={!s().camera?.ok && !s().camera?.error}>
              <p class="card-error">Check the ribbon cable and restart CogniSight.</p>
            </Show>
          </Card>

          <Card
            id="card-recognition"
            title="Recognition"
            tone={s().recognition?.ok ? "ok" : "attention"}
            state={s().recognition?.ok ? "Running" : "Not running"}
          >
            <dl class="card-facts">
              <div>
                <dt>Model</dt>
                <dd>{s().recognition?.model || "Unknown"}</dd>
              </div>
              <div>
                <dt>Face detector</dt>
                <dd>{s().recognition?.detector || "Unknown"}</dd>
              </div>
              <div>
                <dt>Match cutoff</dt>
                <dd>{fixed(s().recognition?.threshold, 2)}</dd>
              </div>
              <div>
                <dt>Seconds per check</dt>
                <dd>{fixed(s().recognition?.seconds_per_check, 1)}</dd>
              </div>
            </dl>
            <Show when={s().recognition?.error}>
              <p class="card-error">{s().recognition.error}</p>
            </Show>
          </Card>

          <Card
            id="card-speech"
            title="Speech"
            tone={!s().speech?.available ? "attention" : s().speech?.enabled ? "ok" : "neutral"}
            state={!s().speech?.available ? "Not available" : s().speech?.enabled ? "On" : "Off"}
          >
            <p class="muted">Introductions spoken into their earphones.</p>
            <Show when={s().speech?.error}>
              <p class="card-error">{s().speech.error}</p>
            </Show>
            <Toggle
              enabled={!!s().speech?.enabled}
              available={!!s().speech?.available}
              onLabel="Turn speech on"
              offLabel="Turn speech off"
              onToggle={toggleSpeech}
            />
          </Card>

          <Card
            id="card-listening"
            title="Listening"
            tone={!s().listening?.available ? "neutral" : s().listening?.enabled ? "ok" : "neutral"}
            state={!s().listening?.available ? "Not available" : s().listening?.enabled ? "On" : "Off"}
          >
            <dl class="card-facts">
              <div>
                <dt>Last heard</dt>
                <dd>{heardText(s().listening?.heard, now())}</dd>
              </div>
            </dl>
            <Show when={s().listening?.error}>
              <p class="card-error">{s().listening.error}</p>
            </Show>
            <Toggle
              enabled={!!s().listening?.enabled}
              // Always allowed, so a microphone plugged in later can be tried again.
              available={true}
              onLabel="Turn listening on"
              offLabel="Turn listening off"
              onToggle={toggleListening}
            />
          </Card>

          <Card id="card-people" title="People" tone="neutral" state={plural(Number(s().people) || 0, "person", "people")}>
            <p class="muted">Saved and ready to be recognised.</p>
            <a class="text-link" href="/people">
              Manage people
            </a>
          </Card>

          <Card id="card-uptime" title="Running for" tone="neutral" state={duration(s().uptime)}>
            <Show when={s().hostname}>
              <p class="muted">Device name: {s().hostname}</p>
            </Show>
          </Card>
        </div>
      </Show>
    </div>
  );
}

import { createEffect, createMemo, createSignal, For, Index, Show } from "solid-js";
import {
  deviceNow,
  getEvents,
  getHome,
  getLive,
  listPeople,
  offline,
  photoUrl,
  setSpeech,
  startGuide,
  stopGuide,
  testSpeech,
} from "./api";
import Camera from "./Camera";
import { useStatus } from "./context";
import { placeName, roomLine, signName, signsOf } from "./signs";
import { HomeIcon, UnknownFace } from "./icons";
import { ago, capitalise, clockTime, isoTime, personHref, plural, useNow, usePoll, useTitle } from "./lib";

const CAPTION_SECONDS = 20;

const KINDS = {
  seen: "Recognised",
  unknown: "Unknown face",
  said: "Said to them",
  heard: "Heard a command",
  room: "Moved room",
  guide: "Guiding",
  system: "Device",
};

function Caption(props) {
  // Keep the last sentence so it can fade out instead of vanishing.
  const [caption, setCaption] = createSignal(null);
  createEffect(() => {
    const said = props.said;
    if (said && typeof said.text === "string" && said.text.trim()) setCaption(said);
  });
  const shown = () => {
    const c = caption();
    return !!c && !offline() && props.now - c.at < CAPTION_SECONDS;
  };
  return (
    <>
      <div class="caption" classList={{ shown: shown() }} aria-hidden="true">
        <p class="caption-text">“{caption()?.text.trim()}”</p>
        <p class="caption-meta">Said to them {ago(caption()?.at, props.now)}</p>
      </div>
      <p class="sr-only" aria-live="polite">
        <Show when={shown()}>Said to them: {caption()?.text}</Show>
      </p>
    </>
  );
}

function Avatar(props) {
  return (
    <Show
      when={props.person?.photos?.length}
      fallback={
        <span class="avatar avatar-initial" aria-hidden="true">
          {(props.name || "?").trim().charAt(0).toUpperCase()}
        </span>
      }
    >
      <img
        class="avatar"
        src={photoUrl(props.person.name, props.person.photos[0])}
        alt=""
        onError={(e) => (e.currentTarget.style.visibility = "hidden")}
      />
    </Show>
  );
}

function WithThemNow(props) {
  const faces = () => (Array.isArray(props.live?.faces) ? props.live.faces.filter(Boolean) : []);
  const known = () => faces().filter((f) => f.name);
  const unknown = () => faces().filter((f) => !f.name).length;
  const stale = () => {
    const updated = props.live?.updated;
    return props.live?.camera && typeof updated === "number" && props.now - updated > 15;
  };

  return (
    <section class="now" aria-labelledby="now-heading">
      <h2 id="now-heading">With them now</h2>
      <Show when={!offline() && roomLine(props.live?.room, props.now)}>
        {(line) => (
          <p class="now-place" classList={{ "is-stale": line().stale }}>
            <HomeIcon />
            <span>{line().text}</span>
          </p>
        )}
      </Show>
      <Show
        when={!offline() && props.live}
        fallback={<p class="now-empty">{offline() ? "Waiting for the device." : "Checking…"}</p>}
      >
        <Show
          when={props.live.camera !== false}
          fallback={<p class="now-empty">The camera is off, so CogniSight can't see who is there.</p>}
        >
          <Show
            when={faces().length}
            fallback={
              <div class="now-empty">
                <p class="now-none">No one in view</p>
                <p class="muted">When someone comes into view, their name appears here.</p>
              </div>
            }
          >
            <ul class="faces" role="list">
              <Index each={known()}>
                {(face) => (
                  <li class="face">
                    <Avatar person={props.people.get(face().name)} name={face().name} />
                    <div>
                      <a class="face-name" href={personHref(face().name)}>
                        {face().name}
                      </a>
                      <p class="face-rel">{face().relationship ? capitalise(face().relationship) : "Recognised"}</p>
                    </div>
                  </li>
                )}
              </Index>
              <Show when={unknown() > 0}>
                <li class="face face-unknown">
                  <span class="avatar avatar-unknown" aria-hidden="true">
                    <UnknownFace />
                  </span>
                  <div>
                    <p class="face-name">
                      {unknown() === 1 ? "Someone they don't know" : `${unknown()} people they don't know`}
                    </p>
                    <p class="face-rel">
                      Should CogniSight know them? <a href="/people?add=1">Add a person</a>
                    </p>
                  </div>
                </li>
              </Show>
            </ul>
          </Show>
        </Show>
        <Show when={stale()}>
          <p class="note-attention">
            Recognition last updated {ago(props.live.updated, props.now)}. If this continues, check the Device page.
          </p>
        </Show>
      </Show>
    </section>
  );
}

function Timeline(props) {
  const startOfToday = () => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    // Shift into the device's clock.
    return d.getTime() / 1000 + (deviceNow() - Date.now() / 1000);
  };
  const events = () => (props.events || []).filter((e) => e && typeof e.at === "number");
  const today = () => events().filter((e) => e.at >= startOfToday());
  const earlier = () => events().filter((e) => e.at < startOfToday());

  const Row = (p) => {
    const kind = () => (KINDS[p.event.kind] ? p.event.kind : "system");
    return (
      <li class={`event k-${kind()}`}>
        <span class="marker" aria-hidden="true" title={KINDS[kind()]} />
        <span class="sr-only">{KINDS[kind()]}: </span>
        <span class="event-text">{p.event.text || KINDS[kind()]}</span>
        <time class="event-time" datetime={isoTime(p.event.at)} title={clockTime(p.event.at)}>
          {ago(p.event.at, props.now)}
        </time>
      </li>
    );
  };

  return (
    <section class="today" aria-labelledby="today-heading">
      <h2 id="today-heading">Today</h2>
      <Show when={props.error && !offline()}>
        <p class="note-attention" role="alert">
          Couldn't load today's activity. {props.error.message}
        </p>
      </Show>
      <Show when={props.loaded} fallback={<p class="muted">Loading today's activity…</p>}>
        <Show
          when={today().length}
          fallback={
            <p class="muted">
              Nothing yet today. When CogniSight recognises someone, reads a sign, or speaks to them, it shows up here.
            </p>
          }
        >
          <ol class="timeline">
            <Index each={today()}>{(event) => <Row event={event()} />}</Index>
          </ol>
        </Show>
        <Show when={earlier().length}>
          <h3 class="earlier">Earlier</h3>
          <ol class="timeline">
            <Index each={earlier()}>{(event) => <Row event={event()} />}</Index>
          </ol>
        </Show>
      </Show>
    </section>
  );
}

function SpeechControls() {
  const status = useStatus();
  const speech = () => status.data()?.speech;
  const [busy, setBusy] = createSignal("");
  const [message, setMessage] = createSignal("");
  const [error, setError] = createSignal("");

  const line = () => {
    const s = speech();
    if (!s) return offline() ? "Waiting for the device." : "Checking…";
    if (!s.available) return `Speech isn't available. ${s.error || "Check that the earphones are paired and connected."}`;
    return s.enabled
      ? "On. CogniSight says who it sees into their earphones."
      : "Off. CogniSight stays quiet until you turn speech back on.";
  };

  async function toggle() {
    const s = speech();
    if (!s) return;
    setBusy("toggle");
    setMessage("");
    setError("");
    try {
      const next = await setSpeech(!s.enabled);
      if (next && typeof next === "object") status.mutate({ ...status.data(), speech: next });
      setMessage(next?.enabled ? "Speech is on." : "Speech is off.");
      status.refresh();
    } catch (err) {
      setError(`Couldn't change speech. ${err.message}`);
    } finally {
      setBusy("");
    }
  }

  async function test() {
    setBusy("test");
    setMessage("");
    setError("");
    try {
      await testSpeech();
      setMessage("Sent a test sentence. They should hear it in their earphones now.");
    } catch (err) {
      setError(`The test didn't play. ${err.message}`);
    } finally {
      setBusy("");
    }
  }

  return (
    <section class="speech" aria-labelledby="speech-heading">
      <div class="speech-text">
        <h2 id="speech-heading" class="h3">
          Speech to the earphones
        </h2>
        <p class="muted">{line()}</p>
      </div>
      <div class="actions">
        <button
          type="button"
          class="button"
          classList={{ primary: speech()?.enabled === false }}
          disabled={!speech()?.available || busy() !== ""}
          onClick={toggle}
        >
          {busy() === "toggle" ? "Changing…" : speech()?.enabled ? "Turn speech off" : "Turn speech on"}
        </button>
        <button type="button" class="button" disabled={busy() !== "" || !speech()} onClick={test}>
          {busy() === "test" ? "Speaking…" : "Test speech"}
        </button>
      </div>
      <div class="speech-feedback">
        <p role="status" class="ok-text">{message()}</p>
        <p role="alert" class="error-text">{error()}</p>
      </div>
    </section>
  );
}

function GuideCard(props) {
  const [destination, setDestination] = createSignal("");
  const [busy, setBusy] = createSignal("");
  const [message, setMessage] = createSignal("");
  const [error, setError] = createSignal("");

  const byId = createMemo(() => new Map(props.signs.map((s) => [s.id, s])));
  const guide = () => (props.guide && typeof props.guide === "object" ? props.guide : null);
  const route = () => (Array.isArray(guide()?.route) ? guide().route.filter(Number.isInteger) : []);
  const atIndex = () => {
    const at = guide()?.at;
    return Number.isInteger(at) ? route().lastIndexOf(at) : -1;
  };
  const destName = () => {
    const d = guide()?.destination;
    return d?.name || signName(byId().get(d?.id), d?.id);
  };
  const arrived = () => {
    const d = guide()?.destination;
    return !!d && Number.isInteger(d.id) && guide().at === d.id;
  };
  // Signs up to and including the last one seen are done; the next one is current.
  const stepState = (i) => (i <= atIndex() ? "done" : i === atIndex() + 1 ? "current" : "todo");

  async function start(event) {
    event.preventDefault();
    setMessage("");
    setError("");
    if (!destination()) {
      setError("Choose the room to guide them to.");
      return;
    }
    setBusy("start");
    try {
      const chosen = byId().get(Number(destination()));
      const next = await startGuide(Number(destination()));
      props.onChange(next && typeof next === "object" ? next : null);
      setMessage(`Guiding them to ${placeName(next?.destination?.name || signName(chosen))}.`);
      setDestination("");
    } catch (err) {
      setError(`Couldn't start guiding. ${err.message}`);
    } finally {
      setBusy("");
    }
  }

  async function stop() {
    setBusy("stop");
    setMessage("");
    setError("");
    try {
      await stopGuide();
      props.onChange(null);
      setMessage("Stopped guiding.");
    } catch (err) {
      setError(`Couldn't stop guiding. ${err.message}`);
    } finally {
      setBusy("");
    }
  }

  return (
    <section class="guide" aria-labelledby="guide-heading">
      <h2 id="guide-heading">{guide() ? `Guiding them to ${placeName(destName())}` : "Guide them to a room"}</h2>
      <Show
        when={guide()}
        fallback={
          <Show
            when={props.signs.length > 1}
            fallback={
              <p class="muted">
                <Show when={props.loaded} fallback="Loading the signs…">
                  Put up at least two signs, with directions between them, to guide them from room to room.{" "}
                  <a href="/home">Go to Home</a>
                </Show>
              </p>
            }
          >
            <form class="guide-form" onSubmit={start} novalidate>
              <label for="guide-to">Guide them to…</label>
              <div class="guide-row">
                <select
                  id="guide-to"
                  class="select"
                  aria-invalid={error() && !destination() ? "true" : undefined}
                  aria-describedby="guide-hint"
                  onChange={(e) => setDestination(e.currentTarget.value)}
                >
                  <option value="" disabled selected={destination() === ""}>
                    Choose a room
                  </option>
                  <For each={props.signs}>
                    {(s) => (
                      <option value={String(s.id)} selected={destination() === String(s.id)}>
                        {signName(s)}
                      </option>
                    )}
                  </For>
                </select>
                <button type="submit" class="button primary" disabled={busy() !== "" || offline()}>
                  {busy() === "start" ? "Starting…" : "Start guiding"}
                </button>
              </div>
              <p id="guide-hint" class="hint">
                They hear one step at each sign on the way.
              </p>
            </form>
          </Show>
        }
      >
        <Show when={route().length} fallback={<p class="muted">No route planned yet.</p>}>
          <ol class="route-steps">
            <For each={route()}>
              {(id, i) => (
                <li class={`step is-${stepState(i())}`} aria-current={stepState(i()) === "current" ? "step" : undefined}>
                  <span class="step-dot" aria-hidden="true" />
                  <span class="step-name">{signName(byId().get(id), id)}</span>
                  <span class="sr-only">
                    {stepState(i()) === "done" ? ", reached" : stepState(i()) === "current" ? ", next" : ""}
                  </span>
                </li>
              )}
            </For>
          </ol>
        </Show>
        <Show when={arrived()}>
          <p class="note-ok">They've reached {placeName(destName())}.</p>
        </Show>
        <Show when={guide().said}>
          <p class="guide-said">
            <span class="muted">Last said: </span>“{guide().said}”
          </p>
        </Show>
        <Show when={Number.isFinite(guide().started)}>
          <p class="muted guide-started">Started {ago(guide().started, props.now)}</p>
        </Show>
        <div class="actions">
          <button type="button" class="button" disabled={busy() !== "" || offline()} onClick={stop}>
            {busy() === "stop" ? "Stopping…" : "Stop guiding"}
          </button>
        </div>
      </Show>
      <div class="speech-feedback">
        <p role="status" class="ok-text">
          {message()}
        </p>
        <p role="alert" class="error-text">
          {error()}
        </p>
      </div>
    </section>
  );
}

export default function Live() {
  useTitle("Live");
  const now = useNow(1000);
  const live = usePoll(getLive, 1000);
  const events = usePoll(() => getEvents(50), 2000);
  const people = usePoll(listPeople, 30000);
  const byName = createMemo(() => new Map((people.data() || []).map((p) => [p.name, p])));
  const home = usePoll(getHome, 10000);
  const signs = () => signsOf(home.data());
  const signsInView = () =>
    (Array.isArray(live.data()?.markers) ? live.data().markers : [])
      .filter((m) => m && Number.isInteger(m.id))
      .map((m) => m.name || `Sign ${m.id}`);
  const setGuide = (guide) => {
    live.mutate({ ...(live.data() || {}), guide });
    live.refresh();
  };

  const known = () => (live.data()?.faces || []).filter((f) => f && f.name).length;

  return (
    <div class="page live">
      <div class="page-head">
        <h1 tabindex="-1">Live</h1>
        <p class="lede">
          What CogniSight sees and says, as it happens.
          <Show when={known() > 0}> {plural(known(), "person", "people")} recognised right now.</Show>
        </p>
      </div>
      <div class="live-grid">
        <div class="live-main">
          <Camera camera={live.data()?.camera} frame={live.data()?.frame}>
            <Caption said={live.data()?.said} now={now()} />
            <Show when={!offline() && signsInView().length}>
              <p class="sign-chip">
                {signsInView().length === 1 ? "Sign in view: " : "Signs in view: "}
                {signsInView().join(", ")}
              </p>
            </Show>
          </Camera>
          <SpeechControls />
        </div>
        <div class="live-side">
          <WithThemNow live={live.data()} people={byName()} now={now()} />
          <GuideCard guide={live.data()?.guide} signs={signs()} loaded={home.loaded()} now={now()} onChange={setGuide} />
          <Timeline events={events.data()} loaded={events.loaded()} error={events.error()} now={now()} />
        </div>
      </div>
    </div>
  );
}

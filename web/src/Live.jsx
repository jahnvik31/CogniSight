import { createEffect, createMemo, createSignal, Index, Show } from "solid-js";
import { deviceNow, getEvents, getLive, listPeople, offline, photoUrl, setSpeech, testSpeech } from "./api";
import Camera from "./Camera";
import { useStatus } from "./context";
import { UnknownFace } from "./icons";
import { ago, capitalise, clockTime, isoTime, personHref, plural, useNow, usePoll, useTitle } from "./lib";

const CAPTION_SECONDS = 20;

const KINDS = {
  seen: "Recognised",
  unknown: "Unknown face",
  said: "Said to them",
  heard: "Heard a command",
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
          fallback={<p class="muted">Nothing yet today. When CogniSight recognises someone or speaks to them, it shows up here.</p>}
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

export default function Live() {
  useTitle("Live");
  const now = useNow(1000);
  const live = usePoll(getLive, 1000);
  const events = usePoll(() => getEvents(50), 2000);
  const people = usePoll(listPeople, 30000);
  const byName = createMemo(() => new Map((people.data() || []).map((p) => [p.name, p])));

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
          </Camera>
          <SpeechControls />
        </div>
        <div class="live-side">
          <WithThemNow live={live.data()} people={byName()} now={now()} />
          <Timeline events={events.data()} loaded={events.loaded()} error={events.error()} now={now()} />
        </div>
      </div>
    </div>
  );
}

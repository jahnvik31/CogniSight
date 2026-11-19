import { createMemo, createSignal, Index, onMount, Show } from "solid-js";
import { useSearchParams } from "@solidjs/router";
import { addSign, getHome, getLive, offline } from "./api";
import { linksOf, roomLine, signName, signsOf, splitNames } from "./signs";
import Marker from "./Marker";
import PlanEditor from "./PlanEditor";
import { ago, plural, useNow, usePoll, useTitle } from "./lib";

function AddSign(props) {
  const [name, setName] = createSignal("");
  const [aliases, setAliases] = createSignal("");
  const [note, setNote] = createSignal("");
  const [nameError, setNameError] = createSignal("");
  const [error, setError] = createSignal("");
  const [saving, setSaving] = createSignal(false);
  let nameInput;

  onMount(() => nameInput?.focus());

  async function save(event) {
    event.preventDefault();
    setError("");
    const trimmed = name().trim();
    if (!trimmed) {
      setNameError("Enter the room's name. It's what they hear when the camera reads the sign.");
      nameInput?.focus();
      return;
    }
    setNameError("");
    setSaving(true);
    try {
      const sign = await addSign({
        name: trimmed,
        aliases: splitNames(aliases()),
        note: note().trim(),
        say_note: false,
      });
      props.onAdded(sign);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <section class="panel add-sign" aria-labelledby="add-sign-heading">
      <div class="panel-head">
        <h2 id="add-sign-heading">Add a sign</h2>
        <p class="muted">Each sign names one room. When the camera reads it, they hear “This is the kitchen.”</p>
      </div>
      <form onSubmit={save} novalidate aria-busy={saving()}>
        <div class="fields">
          <div class="field">
            <label for="sign-name">Room name</label>
            <input
              ref={nameInput}
              id="sign-name"
              autocomplete="off"
              maxlength="40"
              required
              aria-required="true"
              aria-invalid={nameError() ? "true" : undefined}
              aria-describedby="sign-name-hint sign-name-error"
              value={name()}
              onInput={(e) => {
                setName(e.currentTarget.value);
                if (nameError() && e.currentTarget.value.trim()) setNameError("");
              }}
            />
            <p id="sign-name-hint" class="hint">
              Such as Kitchen, Hallway, or Bathroom.
            </p>
            <p id="sign-name-error" class="field-error" role="alert">
              {nameError()}
            </p>
          </div>
          <div class="field">
            <label for="sign-aliases">
              Other names <span class="optional">(optional)</span>
            </label>
            <input
              id="sign-aliases"
              autocomplete="off"
              maxlength="200"
              aria-describedby="sign-aliases-hint"
              value={aliases()}
              onInput={(e) => setAliases(e.currentTarget.value)}
            />
            <p id="sign-aliases-hint" class="hint">
              Other words they might use, separated by commas: toilet, washroom.
            </p>
          </div>
          <div class="field field-wide">
            <label for="sign-note">
              Note <span class="optional">(optional)</span>
            </label>
            <textarea
              id="sign-note"
              rows="2"
              maxlength="300"
              aria-describedby="sign-note-hint"
              value={note()}
              onInput={(e) => setNote(e.currentTarget.value)}
            />
            <p id="sign-note-hint" class="hint">
              Something to remind them here, such as “Your room is the blue door.” You can choose to have it said on the
              sign's page.
            </p>
          </div>
        </div>
        <div class="form-foot">
          <Show when={saving()}>
            <p class="muted" role="status">
              Saving the sign…
            </p>
          </Show>
          <Show when={error()}>
            <p class="error-text" role="alert">
              {error()}
            </p>
          </Show>
          <div class="actions">
            <button type="submit" class="button primary" disabled={saving() || offline()}>
              {saving() ? "Saving…" : "Save sign"}
            </button>
            <button type="button" class="button quiet" onClick={props.onCancel} disabled={saving()}>
              Cancel
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}

export default function Home() {
  useTitle("Home");
  const home = usePoll(getHome, 4000);
  // Live carries which signs are in the frame now, and the freshest room and guide.
  const live = usePoll(getLive, 1500);
  const now = useNow(5000);
  const [params, setParams] = useSearchParams();
  const adding = () => params.add === "1";
  const open = () => setParams({ add: "1" });
  const close = () => setParams({ add: undefined });
  const [added, setAdded] = createSignal(null);
  const [arm, setArm] = createSignal(null);

  const signs = () => signsOf(home.data());
  const links = () => linksOf(home.data());
  const room = () => (live.data() && "room" in live.data() ? live.data().room : home.data()?.room) || null;
  const guide = () => (live.data() && "guide" in live.data() ? live.data().guide : home.data()?.guide) || null;
  const inView = createMemo(
    () => new Set((Array.isArray(live.data()?.markers) ? live.data().markers : []).map((m) => m?.id).filter(Number.isInteger)),
  );
  const waysOut = createMemo(() => {
    const counts = new Map();
    for (const l of links()) counts.set(l.from, (counts.get(l.from) || 0) + 1);
    return counts;
  });

  function onAdded(sign) {
    close();
    setAdded(sign && Number.isInteger(sign.id) ? sign : null);
    if (sign && Number.isInteger(sign.id)) {
      home.mutate({ ...(home.data() || {}), signs: [...signs().filter((s) => s.id !== sign.id), sign] });
      setArm({ id: sign.id });
    }
    home.refresh();
  }

  const seenText = (sign) => {
    if (inView().has(sign.id)) return "In view now";
    return sign.last_seen ? `Last seen ${ago(sign.last_seen, now())}` : "Not seen yet";
  };

  const place = () => roomLine(room(), now());

  return (
    <div class="page home">
      <div class="page-head with-action">
        <div>
          <h1 tabindex="-1">Home</h1>
          <p class="lede">
            Talking signs beside the doors. When the camera reads one, they hear which room they're in.
            <Show when={place()}> {place().text}.</Show>
          </p>
        </div>
        <div class="actions">
          <Show when={!adding()}>
            <button type="button" class="button primary" onClick={open}>
              Add a sign
            </button>
          </Show>
          <Show when={signs().length}>
            <a class="button" href="/home/print">
              Print signs
            </a>
          </Show>
        </div>
      </div>

      <Show when={adding()}>
        <AddSign onCancel={close} onAdded={onAdded} />
      </Show>

      <Show when={added()}>
        <p class="note-ok" role="status">
          {signName(added())} is sign {added().id}.{" "}
          <a href={`/home/print?ids=${added().id}`}>Print it</a>, then tap the plan beside its door to place it.
        </p>
      </Show>

      <Show when={home.error() && !home.loaded() && !offline()}>
        <p class="error-text" role="alert">
          Couldn't load the signs and floor plan. {home.error().message}
        </p>
      </Show>

      <Show when={home.loaded()} fallback={<Show when={!home.error()}><p class="muted">Loading the floor plan…</p></Show>}>
        <div class="home-grid">
          <PlanEditor
            plan={home.data()?.plan ?? null}
            signs={signs()}
            links={links()}
            room={room()}
            guide={guide()}
            inView={inView()}
            arm={arm()}
            onSaved={(plan) => home.mutate({ ...(home.data() || {}), plan })}
          />

          <section class="sign-list" aria-labelledby="signs-heading">
            <h2 id="signs-heading">Signs</h2>
            <Show
              when={signs().length}
              fallback={
                <Show when={!adding()}>
                  <div class="empty empty-compact">
                    <h3>Add the first sign</h3>
                    <p class="muted">
                      Signs go at eye level beside each door, and where the hall splits, so the camera reads them as
                      they walk up.
                    </p>
                    <button type="button" class="button primary" onClick={open}>
                      Add a sign
                    </button>
                  </div>
                </Show>
              }
            >
              <ul class="signs" role="list">
                <Index each={signs()}>
                  {(sign) => (
                    <li class="sign-row" classList={{ "is-in-view": inView().has(sign().id), "is-room": room()?.id === sign().id }}>
                      <Marker id={sign().id} size="52px" />
                      <div class="sign-row-text">
                        <a class="sign-row-name" href={`/home/signs/${sign().id}`}>
                          {signName(sign())}
                        </a>
                        <p class="sign-row-meta">
                          <span classList={{ "in-view": inView().has(sign().id) }}>{seenText(sign())}</span>
                          <span aria-hidden="true"> · </span>
                          <span>
                            {waysOut().get(sign().id) ? plural(waysOut().get(sign().id), "way out", "ways out") : "No ways out yet"}
                          </span>
                        </p>
                      </div>
                    </li>
                  )}
                </Index>
              </ul>
            </Show>
          </section>
        </div>
      </Show>
    </div>
  );
}

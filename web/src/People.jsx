import { createMemo, createSignal, Index, onCleanup, onMount, Show } from "solid-js";
import { useNavigate, useSearchParams } from "@solidjs/router";
import { addPerson, listPeople, offline, photoUrl } from "./api";
import Camera from "./Camera";
import { ago, capitalise, personHref, plural, prepareImage, useNow, usePoll, useTitle } from "./lib";
import { FileButton, isImage } from "./ui";

function AddPerson(props) {
  const navigate = useNavigate();
  const [name, setName] = createSignal("");
  const [relationship, setRelationship] = createSignal("");
  const [note, setNote] = createSignal("");
  const [mode, setMode] = createSignal("device");
  const [file, setFile] = createSignal(null);
  const [nameError, setNameError] = createSignal("");
  const [error, setError] = createSignal("");
  const [conflict, setConflict] = createSignal("");
  const [saving, setSaving] = createSignal(false);
  let nameInput;

  onMount(() => nameInput?.focus());

  const preview = createMemo(() => {
    const f = file();
    if (!f) return null;
    const url = URL.createObjectURL(f);
    onCleanup(() => URL.revokeObjectURL(url));
    return url;
  });

  function choose(f) {
    setError("");
    if (!isImage(f)) {
      setError("That file isn't a photo. Choose a JPG or PNG picture of their face.");
      return;
    }
    setFile(f);
  }

  async function save(event) {
    event.preventDefault();
    setError("");
    setConflict("");
    const trimmed = name().trim();
    if (!trimmed) {
      setNameError("Enter their name. It's what CogniSight will say when it sees them.");
      nameInput?.focus();
      return;
    }
    setNameError("");
    if (mode() === "upload" && !file()) {
      setError("Choose a photo first, or switch to taking one with the device camera.");
      return;
    }
    setSaving(true);
    try {
      const photo = mode() === "upload" ? await prepareImage(file()) : null;
      const saved = await addPerson({
        name: trimmed,
        relationship: relationship().trim(),
        note: note().trim(),
        photo,
      });
      navigate(personHref(saved?.name || trimmed), { state: { added: true } });
    } catch (err) {
      setError(err.message);
      if (err.status === 409) setConflict(trimmed);
      setSaving(false);
    }
  }

  return (
    <section class="panel add-person" aria-labelledby="add-heading">
      <div class="panel-head">
        <h2 id="add-heading">Add a person</h2>
        <p class="muted">CogniSight will introduce them by name when they come into view.</p>
      </div>
      <form onSubmit={save} novalidate aria-busy={saving()}>
        <div class="fields">
          <div class="field">
            <label for="person-name">Name</label>
            <input
              ref={nameInput}
              id="person-name"
              name="name"
              autocomplete="off"
              maxlength="80"
              required
              aria-required="true"
              aria-invalid={nameError() ? "true" : undefined}
              aria-describedby="person-name-hint person-name-error"
              value={name()}
              onInput={(e) => {
                setName(e.currentTarget.value);
                if (nameError() && e.currentTarget.value.trim()) setNameError("");
              }}
            />
            <p id="person-name-hint" class="hint">
              The name CogniSight says, such as Priya.
            </p>
            <p id="person-name-error" class="field-error" role="alert">
              {nameError()}
            </p>
          </div>
          <div class="field">
            <label for="person-rel">
              Relationship <span class="optional">(optional)</span>
            </label>
            <input
              id="person-rel"
              name="relationship"
              autocomplete="off"
              maxlength="80"
              aria-describedby="person-rel-hint"
              value={relationship()}
              onInput={(e) => setRelationship(e.currentTarget.value)}
            />
            <p id="person-rel-hint" class="hint">
              Who they are to them: daughter, neighbour, carer.
            </p>
          </div>
          <div class="field field-wide">
            <label for="person-note">
              Note <span class="optional">(optional)</span>
            </label>
            <textarea
              id="person-note"
              name="note"
              rows="2"
              maxlength="500"
              aria-describedby="person-note-hint"
              value={note()}
              onInput={(e) => setNote(e.currentTarget.value)}
            />
            <p id="person-note-hint" class="hint">
              Anything worth remembering, such as “Visits on Sundays.”
            </p>
          </div>
        </div>

        <fieldset class="choice">
          <legend>Photo</legend>
          <label class="choice-option">
            <input
              type="radio"
              name="photo-source"
              value="device"
              checked={mode() === "device"}
              onChange={() => setMode("device")}
            />
            <span>
              <strong>Take photo with the device camera</strong>
              <span class="muted">They look at CogniSight while you press the button.</span>
            </span>
          </label>
          <label class="choice-option">
            <input
              type="radio"
              name="photo-source"
              value="upload"
              checked={mode() === "upload"}
              onChange={() => setMode("upload")}
            />
            <span>
              <strong>Upload a photo</strong>
              <span class="muted">A clear, recent photo where their face fills most of the picture.</span>
            </span>
          </label>
        </fieldset>

        <Show when={mode() === "device"}>
          <div class="capture">
            <Camera compact alt="Live view from the device camera, for lining up the photo" />
            <p class="muted capture-tip">
              Ask them to face the camera from about an arm's length away, in good light, then press the button.
            </p>
          </div>
        </Show>

        <Show when={mode() === "upload"}>
          <div class="upload">
            <Show when={preview()}>
              <img class="upload-preview" src={preview()} alt={`Chosen photo${name().trim() ? ` of ${name().trim()}` : ""}`} />
            </Show>
            <div class="actions">
              <FileButton class="touch-only" capture="user" onFile={choose} disabled={saving()}>
                {file() ? "Take a different photo" : "Take photo with this phone"}
              </FileButton>
              <FileButton onFile={choose} disabled={saving()}>
                {file() ? "Choose a different photo" : "Choose a photo"}
              </FileButton>
            </div>
          </div>
        </Show>

        <div class="form-foot">
          <Show when={saving()}>
            <p class="muted" role="status">
              {mode() === "device"
                ? "Hold still. The device is taking a photo and checking for a face…"
                : "Saving and checking the photo for a face…"}
            </p>
          </Show>
          <Show when={error()}>
            <p class="error-text" role="alert">
              {error()}
              <Show when={conflict()}>
                {" "}
                <a href={personHref(conflict())}>Open {conflict()}</a>
              </Show>
            </p>
          </Show>
          <div class="actions">
            <button type="submit" class="button primary" disabled={saving() || offline()}>
              {saving()
                ? mode() === "device"
                  ? "Taking photo…"
                  : "Saving…"
                : mode() === "device"
                  ? "Take photo and save person"
                  : "Save person"}
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

export default function People() {
  useTitle("People");
  const people = usePoll(listPeople, 10000);
  const now = useNow(15000);
  const [params, setParams] = useSearchParams();
  const adding = () => params.add === "1";
  const open = () => setParams({ add: "1" });
  const close = () => setParams({ add: undefined });
  const list = () => people.data() || [];

  return (
    <div class="page people">
      <div class="page-head with-action">
        <div>
          <h1 tabindex="-1">People</h1>
          <p class="lede">
            Everyone CogniSight can introduce.
            <Show when={list().length}> {plural(list().length, "person", "people")} saved.</Show>
          </p>
        </div>
        <Show when={!adding() && list().length}>
          <button type="button" class="button primary" onClick={open}>
            Add a person
          </button>
        </Show>
      </div>

      <Show when={adding()}>
        <AddPerson onCancel={close} />
      </Show>

      <Show when={people.error() && !people.loaded() && !offline()}>
        <p class="error-text" role="alert">
          Couldn't load the people saved on the device. {people.error().message}
        </p>
      </Show>

      <Show when={people.loaded()} fallback={<Show when={!people.error()}><p class="muted">Loading people…</p></Show>}>
        <Show
          when={list().length}
          fallback={
            <Show when={!adding()}>
              <div class="empty">
                <h2>Add the first person they should recognise</h2>
                <p class="muted">
                  Start with the people they see most: family, carers, close neighbours. One clear photo is enough to
                  begin.
                </p>
                <button type="button" class="button primary" onClick={open}>
                  Add a person
                </button>
              </div>
            </Show>
          }
        >
          <ul class="people-grid" role="list">
            <Index each={list()}>
              {(person) => (
                <li>
                  <a class="person-tile" href={personHref(person().name)}>
                    <span class="cover">
                      <Show
                        when={person().photos?.length}
                        fallback={
                          <span class="cover-initial" aria-hidden="true">
                            {(person().name || "?").charAt(0).toUpperCase()}
                          </span>
                        }
                      >
                        <img src={photoUrl(person().name, person().photos[0])} alt="" loading="lazy" />
                      </Show>
                    </span>
                    <span class="tile-name">{person().name}</span>
                    <span class="tile-rel">{person().relationship ? capitalise(person().relationship) : "No relationship added"}</span>
                    <span class="tile-seen">
                      {person().last_seen ? `Last seen ${ago(person().last_seen, now())}` : "Not seen yet"}
                    </span>
                  </a>
                </li>
              )}
            </Index>
          </ul>
        </Show>
      </Show>
    </div>
  );
}

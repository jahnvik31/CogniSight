import { createEffect, createSignal, For, on, Show } from "solid-js";
import { useLocation, useNavigate, useParams } from "@solidjs/router";
import { addPhoto, deletePerson, deletePhoto, listPeople, offline, photoUrl, updatePerson } from "./api";
import Camera from "./Camera";
import { ago, capitalise, plural, prepareImage, safeDecode, useNow, usePoll, useTitle } from "./lib";
import { ConfirmAction, FileButton, isImage } from "./ui";

export default function Person() {
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const name = () => safeDecode(params.name || "");
  const people = usePoll(listPeople, 10000);
  const now = useNow(15000);
  const person = () => people.data()?.find((p) => p.name === name());
  const missing = () => people.loaded() && !person();
  const photos = () => person()?.photos || [];

  useTitle(() => (missing() ? "Not found" : person()?.name || name()));

  // Replace this person in the cached list with what the device sent back.
  function store(updated) {
    if (!updated || typeof updated !== "object" || !updated.name) return;
    people.mutate((people.data() || []).map((p) => (p.name === updated.name ? updated : p)));
    people.refresh();
  }

  // Photo adding
  const [capturing, setCapturing] = createSignal(false);
  const [photoBusy, setPhotoBusy] = createSignal("");
  const [photoMessage, setPhotoMessage] = createSignal("");
  const [photoError, setPhotoError] = createSignal("");

  async function sendPhoto(file) {
    setPhotoError("");
    setPhotoMessage("");
    if (file && !isImage(file)) {
      setPhotoError("That file isn't a photo. Choose a JPG or PNG picture of their face.");
      return;
    }
    setPhotoBusy(file ? "upload" : "device");
    try {
      const photo = file ? await prepareImage(file) : null;
      const updated = await addPhoto(name(), photo);
      store(updated);
      setPhotoMessage("Photo added.");
    } catch (err) {
      setPhotoError(err.message);
    } finally {
      setPhotoBusy("");
    }
  }

  // Details editing
  const [relationship, setRelationship] = createSignal("");
  const [note, setNote] = createSignal("");
  const [detailsBusy, setDetailsBusy] = createSignal(false);
  const [detailsMessage, setDetailsMessage] = createSignal("");
  const [detailsError, setDetailsError] = createSignal("");
  let loadedFor = null;

  createEffect(() => {
    const p = person();
    if (p && loadedFor !== p.name) {
      loadedFor = p.name;
      setRelationship(p.relationship || "");
      setNote(p.note || "");
    }
  });

  // Moving to another person's page reuses this component; start fresh.
  createEffect(
    on(
      name,
      () => {
        setCapturing(false);
        setPhotoMessage("");
        setPhotoError("");
        setDetailsMessage("");
        setDetailsError("");
      },
      { defer: true },
    ),
  );

  const dirty = () =>
    !!person() && (relationship() !== (person().relationship || "") || note() !== (person().note || ""));

  async function saveDetails(event) {
    event.preventDefault();
    if (!dirty()) return;
    setDetailsBusy(true);
    setDetailsMessage("");
    setDetailsError("");
    try {
      const updated = await updatePerson(name(), {
        relationship: relationship().trim(),
        note: note().trim(),
      });
      store(updated);
      if (updated) {
        setRelationship(updated.relationship || "");
        setNote(updated.note || "");
      }
      setDetailsMessage("Changes saved.");
    } catch (err) {
      setDetailsError(`Couldn't save the changes. ${err.message}`);
    } finally {
      setDetailsBusy(false);
    }
  }

  async function removePerson() {
    await deletePerson(name());
    navigate("/people", { replace: true });
  }

  async function removePhoto(filename) {
    setPhotoMessage("");
    await deletePhoto(name(), filename);
    people.mutate(
      (people.data() || []).map((p) =>
        p.name === name() ? { ...p, photos: (p.photos || []).filter((f) => f !== filename) } : p,
      ),
    );
    people.refresh();
    setPhotoMessage("Photo deleted.");
  }

  const photoAdvice = () => {
    const n = photos().length;
    if (n === 0) return "There are no photos yet, so CogniSight can't recognise them. Add one below.";
    if (n < 3) return `Add ${plural(3 - n, "more photo")} for steadier recognition.`;
    return null;
  };

  return (
    <div class="page person">
      <a class="back" href="/people">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
          <path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        All people
      </a>

      <Show when={!people.loaded()}>
        <Show
          when={people.error() && !offline()}
          fallback={
            <h1 tabindex="-1" class="loading-title">
              {name()}
            </h1>
          }
        >
          <h1 tabindex="-1">{name()}</h1>
          <p class="error-text" role="alert">
            Couldn't load this person. {people.error().message}
          </p>
        </Show>
      </Show>

      <Show when={missing()}>
        <div class="empty">
          <h1 tabindex="-1">No one called {name()} is saved</h1>
          <p class="muted">They may have been deleted. You can add them again from the people list.</p>
          <a class="button primary" href="/people">
            Go to people
          </a>
        </div>
      </Show>

      <Show when={person()}>
        <header class="person-head">
          <Show
            when={photos().length}
            fallback={
              <span class="avatar avatar-large avatar-initial" aria-hidden="true">
                {(person().name || "?").charAt(0).toUpperCase()}
              </span>
            }
          >
            <img class="avatar avatar-large" src={photoUrl(person().name, photos()[0])} alt="" />
          </Show>
          <div>
            <h1 tabindex="-1">{person().name}</h1>
            <p class="person-rel">{person().relationship ? capitalise(person().relationship) : "No relationship added"}</p>
            <p class="muted">{person().last_seen ? `Last seen ${ago(person().last_seen, now())}` : "Not seen by the camera yet"}</p>
          </div>
        </header>

        <Show when={location.state?.added}>
          <p class="note-ok" role="status">
            {person().name} is saved. CogniSight will introduce them when they come into view.
          </p>
        </Show>

        <section class="block" aria-labelledby="photos-heading">
          <div class="block-head">
            <h2 id="photos-heading">Photos</h2>
            <p class="muted">3–5 photos from slightly different angles make recognition steadier.</p>
            <Show when={photoAdvice()}>
              <p class="note-attention">{photoAdvice()}</p>
            </Show>
          </div>

          <Show when={photos().length}>
            <ul class="photo-grid" role="list">
              <For each={photos()}>
                {(filename, i) => (
                  <li class="photo">
                    <img
                      src={photoUrl(person().name, filename)}
                      alt={`Photo ${i() + 1} of ${person().name}`}
                      loading="lazy"
                    />
                    <ConfirmAction
                      label="Delete photo"
                      question={
                        photos().length === 1
                          ? "Delete their only photo? CogniSight won't recognise them until you add another."
                          : "Delete this photo?"
                      }
                      confirmLabel="Delete photo"
                      onConfirm={() => removePhoto(filename)}
                    />
                  </li>
                )}
              </For>
            </ul>
          </Show>

          <div class="add-photo">
            <h3>Add a photo</h3>
            <div class="actions">
              <button
                type="button"
                class="button"
                classList={{ primary: !capturing() }}
                aria-expanded={capturing()}
                aria-controls="device-capture"
                disabled={photoBusy() !== ""}
                onClick={() => setCapturing(!capturing())}
              >
                {capturing() ? "Close the device camera" : "Take photo with the device camera"}
              </button>
              <FileButton class="touch-only" capture="user" onFile={sendPhoto} disabled={photoBusy() !== ""}>
                Take photo with this phone
              </FileButton>
              <FileButton onFile={sendPhoto} disabled={photoBusy() !== ""}>
                Upload a photo
              </FileButton>
            </div>

            <Show when={capturing()}>
              <div class="capture" id="device-capture">
                <Camera compact alt={`Live view from the device camera, for a photo of ${person().name}`} />
                <div class="capture-side">
                  <p class="muted">
                    Ask {person().name} to face the camera from about an arm's length away. Turn their head a little
                    between photos.
                  </p>
                  <button
                    type="button"
                    class="button primary"
                    disabled={photoBusy() !== "" || offline()}
                    onClick={() => sendPhoto(null)}
                  >
                    {photoBusy() === "device" ? "Taking photo…" : "Take photo"}
                  </button>
                </div>
              </div>
            </Show>

            <div class="feedback">
              <p role="status" class="muted">
                {photoBusy() === "device"
                  ? "Hold still. The device is taking a photo and checking for a face…"
                  : photoBusy() === "upload"
                    ? "Saving the photo and checking for a face…"
                    : photoMessage()}
              </p>
              <p role="alert" class="error-text">
                {photoError()}
              </p>
            </div>
          </div>
        </section>

        <section class="block" aria-labelledby="details-heading">
          <div class="block-head">
            <h2 id="details-heading">Details</h2>
          </div>
          <form class="details-form" onSubmit={saveDetails}>
            <div class="field">
              <label for="edit-rel">Relationship</label>
              <input
                id="edit-rel"
                autocomplete="off"
                maxlength="80"
                aria-describedby="edit-rel-hint"
                value={relationship()}
                onInput={(e) => setRelationship(e.currentTarget.value)}
              />
              <p id="edit-rel-hint" class="hint">
                Who they are to them: daughter, neighbour, carer.
              </p>
            </div>
            <div class="field">
              <label for="edit-note">Note</label>
              <textarea
                id="edit-note"
                rows="3"
                maxlength="500"
                value={note()}
                onInput={(e) => setNote(e.currentTarget.value)}
              />
            </div>
            <div class="form-foot">
              <div class="actions">
                <button type="submit" class="button primary" disabled={!dirty() || detailsBusy()}>
                  {detailsBusy() ? "Saving…" : "Save changes"}
                </button>
              </div>
              <p role="status" class="ok-text">
                {dirty() ? "" : detailsMessage()}
              </p>
              <p role="alert" class="error-text">
                {detailsError()}
              </p>
            </div>
          </form>
        </section>

        <section class="block block-danger" aria-labelledby="remove-heading">
          <div class="block-head">
            <h2 id="remove-heading">Remove {person().name}</h2>
            <p class="muted">CogniSight will stop recognising them.</p>
          </div>
          <ConfirmAction
            label={`Delete ${person().name}`}
            question={`Delete ${person().name} and ${plural(photos().length, "photo")}? This can't be undone.`}
            confirmLabel={`Delete ${person().name}`}
            onConfirm={removePerson}
          />
        </section>
      </Show>
    </div>
  );
}

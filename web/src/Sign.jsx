import { createEffect, createMemo, createSignal, For, Index, on, Show } from "solid-js";
import { useNavigate, useParams } from "@solidjs/router";
import { deleteSign, getHome, offline, saveLinks, updateSign } from "./api";
import { arrivalSentence, linksOf, placeName, signName, signsOf, splitNames } from "./signs";
import Marker from "./Marker";
import { ago, useNow, usePoll, useTitle } from "./lib";
import { ConfirmAction } from "./ui";

export default function Sign() {
  const params = useParams();
  const navigate = useNavigate();
  const id = () => (/^\d+$/.test(params.id || "") ? Number(params.id) : NaN);
  const home = usePoll(getHome, 5000);
  const now = useNow(15000);
  const signs = () => signsOf(home.data());
  const links = () => linksOf(home.data());
  const sign = () => signs().find((s) => s.id === id());
  const missing = () => home.loaded() && !sign();
  const byId = createMemo(() => new Map(signs().map((s) => [s.id, s])));
  const others = () => signs().filter((s) => s.id !== id());

  useTitle(() => (missing() ? "Sign not found" : sign() ? signName(sign()) : "Sign"));

  function storeSign(updated) {
    if (!updated || typeof updated !== "object" || !Number.isInteger(updated.id)) return;
    home.mutate({ ...home.data(), signs: signs().map((s) => (s.id === updated.id ? updated : s)) });
    home.refresh();
  }

  // Details
  const [name, setName] = createSignal("");
  const [aliases, setAliases] = createSignal("");
  const [note, setNote] = createSignal("");
  const [sayNote, setSayNote] = createSignal(false);
  const [detailsBusy, setDetailsBusy] = createSignal(false);
  const [detailsMessage, setDetailsMessage] = createSignal("");
  const [detailsError, setDetailsError] = createSignal("");
  const [nameError, setNameError] = createSignal("");

  // Ways
  let rowKey = 0;
  const [rows, setRows] = createSignal([]);
  const [waysBusy, setWaysBusy] = createSignal(false);
  const [waysMessage, setWaysMessage] = createSignal("");
  const [waysError, setWaysError] = createSignal("");
  const [invalid, setInvalid] = createSignal(new Set());

  const outgoing = () => links().filter((l) => l.from === id());
  const rowsFrom = (list) => list.map((l) => ({ key: ++rowKey, to: String(l.to), text: l.text || "" }));

  let loadedFor = null;
  createEffect(() => {
    const s = sign();
    if (s && loadedFor !== s.id) {
      loadedFor = s.id;
      setName(s.name || "");
      setAliases((Array.isArray(s.aliases) ? s.aliases : []).join(", "));
      setNote(s.note || "");
      setSayNote(!!s.say_note);
      setRows(rowsFrom(outgoing()));
    }
  });

  // Moving to another sign's page reuses this component; start fresh.
  createEffect(
    on(
      id,
      () => {
        setDetailsMessage("");
        setDetailsError("");
        setNameError("");
        setWaysMessage("");
        setWaysError("");
        setInvalid(new Set());
      },
      { defer: true },
    ),
  );

  const detailsDirty = () => {
    const s = sign();
    if (!s) return false;
    return (
      name().trim() !== (s.name || "") ||
      splitNames(aliases()).join(",") !== (Array.isArray(s.aliases) ? s.aliases : []).join(",") ||
      note().trim() !== (s.note || "") ||
      sayNote() !== !!s.say_note
    );
  };

  async function saveDetails(event) {
    event.preventDefault();
    if (!detailsDirty()) return;
    const trimmed = name().trim();
    if (!trimmed) {
      setNameError("Enter the room's name. It's what they hear when the camera reads the sign.");
      return;
    }
    setNameError("");
    setDetailsBusy(true);
    setDetailsMessage("");
    setDetailsError("");
    try {
      const updated = await updateSign(id(), {
        name: trimmed,
        aliases: splitNames(aliases()),
        note: note().trim(),
        say_note: sayNote(),
      });
      storeSign(updated);
      if (updated && typeof updated === "object") {
        setName(updated.name || trimmed);
        setAliases((Array.isArray(updated.aliases) ? updated.aliases : []).join(", "));
        setNote(updated.note || "");
        setSayNote(!!updated.say_note);
      }
      setDetailsMessage("Changes saved.");
    } catch (err) {
      setDetailsError(`Couldn't save the changes. ${err.message}`);
    } finally {
      setDetailsBusy(false);
    }
  }

  const spoken = () => {
    const first = arrivalSentence(name().trim() || sign()?.name);
    return sayNote() && note().trim() ? `${first} ${note().trim()}` : first;
  };

  // Ways from this sign
  const cleanRows = () =>
    rows()
      .map((r) => ({ to: r.to, text: r.text.trim() }))
      .filter((r) => r.to !== "" || r.text !== "");
  const waysDirty = () =>
    JSON.stringify(cleanRows().map((r) => [Number(r.to), r.text])) !==
    JSON.stringify(outgoing().map((l) => [l.to, (l.text || "").trim()]));

  const updateRow = (index, patch) => setRows(rows().map((r, i) => (i === index ? { ...r, ...patch } : r)));
  const addRow = () => {
    setRows([...rows(), { key: ++rowKey, to: "", text: "" }]);
    queueMicrotask(() => document.getElementById(`way-to-${rows().length - 1}`)?.focus());
  };
  const removeRow = (index) => {
    setRows(rows().filter((_, i) => i !== index));
    setInvalid(new Set());
  };

  async function saveWays(event) {
    event.preventDefault();
    setWaysMessage("");
    setWaysError("");
    const list = rows();
    const bad = new Set();
    const seen = new Set();
    let problem = "";
    list.forEach((r, i) => {
      const text = r.text.trim();
      if (r.to === "" && text === "") return;
      const where = byId().get(Number(r.to));
      if (r.to === "") {
        bad.add(i);
        problem ||= "Choose where each way goes.";
      } else if (!text) {
        bad.add(i);
        problem ||= `Write the directions for the way to ${placeName(signName(where, Number(r.to)))}.`;
      } else if (seen.has(r.to)) {
        bad.add(i);
        problem ||= `There are two ways to ${placeName(signName(where, Number(r.to)))}. Keep one.`;
      }
      seen.add(r.to);
    });
    setInvalid(bad);
    if (problem) {
      setWaysError(problem);
      return;
    }
    setWaysBusy(true);
    try {
      const payload = cleanRows().map((r) => ({ to: Number(r.to), text: r.text }));
      const all = await saveLinks(id(), payload);
      home.mutate({ ...home.data(), links: all });
      setRows(rowsFrom(all.filter((l) => l.from === id())));
      home.refresh();
      setWaysMessage("Directions saved.");
    } catch (err) {
      setWaysError(`Couldn't save the directions. ${err.message}`);
    } finally {
      setWaysBusy(false);
    }
  }

  const reverseOf = (to) => links().find((l) => l.from === Number(to) && l.to === id());

  async function remove() {
    await deleteSign(id());
    navigate("/home", { replace: true });
  }

  return (
    <div class="page sign-page">
      <a class="back" href="/home">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
          <path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        Home
      </a>

      <Show when={!home.loaded()}>
        <Show
          when={home.error() && !offline()}
          fallback={
            <h1 tabindex="-1" class="loading-title">
              Sign {params.id}
            </h1>
          }
        >
          <h1 tabindex="-1">Sign {params.id}</h1>
          <p class="error-text" role="alert">
            Couldn't load this sign. {home.error().message}
          </p>
        </Show>
      </Show>

      <Show when={missing()}>
        <div class="empty">
          <h1 tabindex="-1">There's no sign {params.id}</h1>
          <p class="muted">It may have been deleted. The Home page lists every sign.</p>
          <a class="button primary" href="/home">
            Go to Home
          </a>
        </div>
      </Show>

      <Show when={sign()}>
        <header class="sign-head">
          <Marker id={sign().id} size="88px" />
          <div>
            <h1 tabindex="-1">{signName(sign())}</h1>
            <p class="muted">
              Sign {sign().id} · {sign().last_seen ? `Last seen ${ago(sign().last_seen, now())}` : "Not seen by the camera yet"}
            </p>
          </div>
        </header>

        <section class="block" aria-labelledby="sign-details-heading">
          <div class="block-head">
            <h2 id="sign-details-heading">Details</h2>
          </div>
          <form class="details-form" onSubmit={saveDetails} novalidate>
            <div class="field">
              <label for="edit-sign-name">Name</label>
              <input
                id="edit-sign-name"
                autocomplete="off"
                maxlength="40"
                required
                aria-required="true"
                aria-invalid={nameError() ? "true" : undefined}
                aria-describedby="edit-sign-name-error"
                value={name()}
                onInput={(e) => {
                  setName(e.currentTarget.value);
                  if (nameError() && e.currentTarget.value.trim()) setNameError("");
                }}
              />
              <p id="edit-sign-name-error" class="field-error" role="alert">
                {nameError()}
              </p>
            </div>
            <div class="field">
              <span class="field-label">Said on arrival</span>
              <p class="said-preview">
                “{spoken()}”
              </p>
            </div>
            <div class="field">
              <label for="edit-sign-note">Note</label>
              <textarea
                id="edit-sign-note"
                rows="2"
                maxlength="300"
                aria-describedby="edit-sign-note-hint"
                value={note()}
                onInput={(e) => setNote(e.currentTarget.value)}
              />
              <p id="edit-sign-note-hint" class="hint">
                Such as “Your room is the blue door.”
              </p>
            </div>
            <label class="check">
              <input type="checkbox" checked={sayNote()} onChange={(e) => setSayNote(e.currentTarget.checked)} />
              <span>Say the note when they arrive</span>
            </label>
            <div class="field">
              <label for="edit-sign-aliases">Other names</label>
              <input
                id="edit-sign-aliases"
                autocomplete="off"
                maxlength="200"
                aria-describedby="edit-sign-aliases-hint"
                value={aliases()}
                onInput={(e) => setAliases(e.currentTarget.value)}
              />
              <p id="edit-sign-aliases-hint" class="hint">
                Other words they might use for this room, separated by commas: toilet, washroom.
              </p>
            </div>
            <div class="form-foot">
              <div class="actions">
                <button type="submit" class="button primary" disabled={!detailsDirty() || detailsBusy() || offline()}>
                  {detailsBusy() ? "Saving…" : "Save changes"}
                </button>
              </div>
              <p role="status" class="ok-text">
                {detailsDirty() ? "" : detailsMessage()}
              </p>
              <p role="alert" class="error-text">
                {detailsError()}
              </p>
            </div>
          </form>
        </section>

        <section class="block" aria-labelledby="ways-heading">
          <div class="block-head">
            <h2 id="ways-heading">Ways from this sign</h2>
            <p class="muted">
              One sentence for each room they can reach from here, written for someone standing in front of this sign.
              They hear it when the camera reads this sign on the way.
            </p>
          </div>
          <form class="ways-form" onSubmit={saveWays} novalidate>
            <fieldset class="ways">
              <legend>With this sign in front of you…</legend>
              <Show
                when={rows().length}
                fallback={<p class="muted">No ways from here yet. Add one for each room they might walk to next.</p>}
              >
                <ol class="way-list">
                  <Index each={rows()}>
                    {(row, i) => {
                      const dest = () => byId().get(Number(row().to));
                      const reverse = () => (row().to !== "" ? reverseOf(row().to) : undefined);
                      return (
                        <li class="way">
                          <div class="way-fields">
                            <div class="field way-to">
                              <label for={`way-to-${i}`}>To</label>
                              <select
                                id={`way-to-${i}`}
                                class="select"
                                aria-invalid={invalid().has(i) ? "true" : undefined}
                                value={row().to}
                                onChange={(e) => updateRow(i, { to: e.currentTarget.value })}
                              >
                                <option value="" disabled selected={row().to === ""}>
                                  Choose a room
                                </option>
                                <Show when={row().to !== "" && !dest()}>
                                  <option value={row().to} selected>
                                    Sign {row().to} (deleted)
                                  </option>
                                </Show>
                                <For each={others()}>
                                  {(s) => (
                                    <option value={String(s.id)} selected={row().to === String(s.id)}>
                                      {signName(s)}
                                    </option>
                                  )}
                                </For>
                              </select>
                            </div>
                            <div class="field way-text">
                              <label for={`way-text-${i}`}>Directions</label>
                              <input
                                id={`way-text-${i}`}
                                autocomplete="off"
                                maxlength="240"
                                placeholder="The bathroom is the second door on your right."
                                aria-invalid={invalid().has(i) ? "true" : undefined}
                                value={row().text}
                                onInput={(e) => updateRow(i, { text: e.currentTarget.value })}
                              />
                            </div>
                            <button
                              type="button"
                              class="button quiet danger way-remove"
                              aria-label={dest() ? `Remove the way to ${placeName(signName(dest()))}` : "Remove this way"}
                              onClick={() => removeRow(i)}
                            >
                              Remove
                            </button>
                          </div>
                          <Show when={dest()}>
                            <Show
                              when={reverse()}
                              fallback={
                                <p class="way-back hint">
                                  No way back yet.{" "}
                                  <a href={`/home/signs/${dest().id}`}>Add one on the {signName(dest())} sign</a>.
                                </p>
                              }
                            >
                              <p class="way-back hint">
                                Coming back, at the <a href={`/home/signs/${dest().id}`}>{signName(dest())}</a> sign: “
                                {reverse().text}”
                              </p>
                            </Show>
                          </Show>
                        </li>
                      );
                    }}
                  </Index>
                </ol>
              </Show>
            </fieldset>
            <Show when={!others().length}>
              <p class="note-attention">Add another sign on the Home page first. Directions always lead to another sign.</p>
            </Show>
            <div class="form-foot">
              <div class="actions">
                <button type="button" class="button" onClick={addRow} disabled={!others().length}>
                  Add a way
                </button>
                <button type="submit" class="button primary" disabled={!waysDirty() || waysBusy() || offline()}>
                  {waysBusy() ? "Saving…" : "Save directions"}
                </button>
              </div>
              <p role="status" class="ok-text">
                {waysDirty() ? "" : waysMessage()}
              </p>
              <p role="alert" class="error-text">
                {waysError()}
              </p>
            </div>
          </form>
        </section>

        <section class="block" aria-labelledby="print-heading">
          <div class="block-head">
            <h2 id="print-heading">The printed sign</h2>
            <p class="muted">Put it at eye level beside the door, where they'll face it as they walk up.</p>
          </div>
          <div class="sign-print">
            <Marker id={sign().id} size="200px" label={`Marker for sign ${sign().id}, ${signName(sign())}`} class="marker-large" />
            <a class="button primary" href={`/home/print?ids=${sign().id}`}>
              Print this sign
            </a>
          </div>
        </section>

        <section class="block block-danger" aria-labelledby="remove-sign-heading">
          <div class="block-head">
            <h2 id="remove-sign-heading">Remove this sign</h2>
            <p class="muted">Its directions and its place on the floor plan are removed too.</p>
          </div>
          <ConfirmAction
            label="Delete sign"
            question={`Delete the ${signName(sign())} sign? This can't be undone. Take the printed sign off the wall too.`}
            confirmLabel="Delete sign"
            onConfirm={remove}
          />
        </section>
      </Show>
    </div>
  );
}

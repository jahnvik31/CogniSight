import { createSignal, Show } from "solid-js";

// A button that opens the file picker (or, with capture="user", the phone's camera).
export function FileButton(props) {
  return (
    <label
      class={`button file-button ${props.class || ""}`}
      classList={{ "is-disabled": !!props.disabled }}
    >
      <input
        type="file"
        class="sr-only"
        accept="image/*"
        capture={props.capture}
        disabled={props.disabled}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          // Clear it so picking the same file again still counts as a change.
          event.currentTarget.value = "";
          if (file) props.onFile(file);
        }}
      />
      {props.children}
    </label>
  );
}

export function isImage(file) {
  return !!file && (!file.type || file.type.startsWith("image/"));
}

// A destructive action that asks before it runs, in place, without a pop-up.
export function ConfirmAction(props) {
  const [asking, setAsking] = createSignal(false);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  let trigger;
  let cancel;

  const ask = () => {
    setError("");
    setAsking(true);
    queueMicrotask(() => cancel?.focus());
  };
  const stop = () => {
    setAsking(false);
    setError("");
    queueMicrotask(() => trigger?.focus());
  };
  const run = async () => {
    setBusy(true);
    setError("");
    try {
      await props.onConfirm();
    } catch (err) {
      setError(err?.message || "That didn't work. Try again.");
      setBusy(false);
      return;
    }
    setBusy(false);
    setAsking(false);
  };

  return (
    <div class={`confirm ${props.class || ""}`}>
      <Show
        when={asking()}
        fallback={
          <button ref={trigger} type="button" class="button quiet danger" onClick={ask}>
            {props.label}
          </button>
        }
      >
        <div class="confirm-box" role="group" aria-label={props.question}>
          <p>{props.question}</p>
          <div class="actions">
            <button type="button" class="button danger-fill" disabled={busy()} onClick={run}>
              {busy() ? props.busyLabel || "Deleting…" : props.confirmLabel}
            </button>
            <button ref={cancel} type="button" class="button" disabled={busy()} onClick={stop}>
              Cancel
            </button>
          </div>
        </div>
      </Show>
      <Show when={error()}>
        <p class="error-text" role="alert">
          {error()}
        </p>
      </Show>
    </div>
  );
}

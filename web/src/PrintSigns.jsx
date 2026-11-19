import { For, Show } from "solid-js";
import { useSearchParams } from "@solidjs/router";
import { getHome, offline } from "./api";
import { signName, signsOf } from "./signs";
import Marker from "./Marker";
import { plural, usePoll, useTitle } from "./lib";

// One A4 sheet per sign. The marker is 14 cm across, with a one-cell white margin
// (about 2.3 cm) so the camera can find its edge.
export default function PrintSigns() {
  useTitle("Print signs");
  const [params] = useSearchParams();
  const home = usePoll(getHome, 30000);

  const wanted = () => {
    const raw = typeof params.ids === "string" ? params.ids : "";
    if (!raw.trim()) return null;
    return raw
      .split(",")
      .map((s) => s.trim())
      .filter((s) => /^\d+$/.test(s))
      .map(Number);
  };

  const sheets = () => {
    const all = signsOf(home.data());
    const ids = wanted();
    if (!ids) return all;
    const byId = new Map(all.map((s) => [s.id, s]));
    return ids.map((id) => byId.get(id)).filter(Boolean);
  };

  const nameSize = (name) => {
    const n = (name || "").length;
    if (n <= 9) return "name-xl";
    if (n <= 16) return "name-l";
    return "name-m";
  };

  return (
    <div class="page print-page">
      <div class="print-hide">
        <a class="back" href="/home">
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
            <path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          Home
        </a>
        <div class="page-head with-action">
          <div>
            <h1 tabindex="-1">Print signs</h1>
            <p class="lede">
              One sign on each A4 sheet. Print at 100% size, not “fit to page”, so each marker comes out about 14 cm
              across. Use plain white paper and avoid glossy lamination, which can glare.
            </p>
          </div>
          <Show when={sheets().length}>
            <button type="button" class="button primary" onClick={() => window.print()}>
              Print
            </button>
          </Show>
        </div>

        <Show when={home.error() && !home.loaded() && !offline()}>
          <p class="error-text" role="alert">
            Couldn't load the signs. {home.error().message}
          </p>
        </Show>
        <Show when={!home.loaded() && !home.error()}>
          <p class="muted">Loading the signs…</p>
        </Show>
        <Show when={home.loaded()}>
          <Show
            when={sheets().length}
            fallback={
              <div class="empty">
                <h2>{wanted() ? "Those signs weren't found" : "There are no signs to print yet"}</h2>
                <p class="muted">Add signs on the Home page, then print them from there.</p>
                <a class="button primary" href="/home">
                  Go to Home
                </a>
              </div>
            }
          >
            <p class="muted print-count">{plural(sheets().length, "sheet")} to print.</p>
          </Show>
        </Show>
      </div>

      <div class="sheets">
        <For each={sheets()}>
          {(sign) => (
            <article class="sheet" aria-label={`Sheet for sign ${sign.id}, ${signName(sign)}`}>
              <Marker id={sign.id} class="sheet-marker" quiet={1} label={`Marker for sign ${sign.id}`} />
              <p class={`sheet-name ${nameSize(signName(sign))}`}>{signName(sign)}</p>
              <p class="sheet-line">CogniSight sign {sign.id}. Keep this at eye level beside the door.</p>
            </article>
          )}
        </For>
      </div>
    </div>
  );
}

import { createEffect, For, on, Show } from "solid-js";
import { useLocation } from "@solidjs/router";
import { getStatus, offline } from "./api";
import { StatusContext } from "./context";
import { usePoll } from "./lib";
import { DeviceIcon, HomeIcon, LiveIcon, PeopleIcon, PlaceIcon } from "./icons";

const TABS = [
  { href: "/", label: "Live", Icon: LiveIcon },
  { href: "/people", label: "People", Icon: PeopleIcon },
  { href: "/home", label: "Home", Icon: HomeIcon },
  { href: "/place", label: "Place", Icon: PlaceIcon },
  { href: "/device", label: "Device", Icon: DeviceIcon },
];

function current(pathname, href) {
  if (href === "/") return pathname === "/" ? "page" : undefined;
  if (pathname === href) return "page";
  if (pathname.startsWith(href + "/")) return "true";
  return undefined;
}

function DeviceState(props) {
  const ok = () => !offline() && props.status.data()?.camera?.ok === true;
  const text = () => {
    if (offline()) return "Not connected";
    const data = props.status.data();
    if (!data) return "Connecting…";
    return data.camera?.ok ? "Camera on" : "Camera off";
  };
  return (
    <p class="device-state" classList={{ "is-ok": ok() }}>
      <span class="dot" aria-hidden="true" />
      <span>{text()}</span>
    </p>
  );
}

export default function Layout(props) {
  const location = useLocation();
  const status = usePoll(getStatus, 3000);

  // Move focus to the new page heading after navigating, for keyboard and screen reader users.
  createEffect(
    on(
      () => location.pathname,
      () => {
        requestAnimationFrame(() => document.querySelector("main h1")?.focus({ preventScroll: true }));
      },
      { defer: true },
    ),
  );

  return (
    <StatusContext.Provider value={status}>
      <a class="skip" href="#main">Skip to content</a>
      <div class="app">
        <header class="rail">
          <a class="wordmark" href="/">
            Cogni<span>Sight</span>
          </a>
          <DeviceState status={status} />
          <nav class="tabs" aria-label="Main">
            <For each={TABS}>
              {(tab) => (
                <a href={tab.href} aria-current={current(location.pathname, tab.href)}>
                  <tab.Icon />
                  <span>{tab.label}</span>
                </a>
              )}
            </For>
          </nav>
        </header>
        <main id="main" class="main">
          <div class="banner-slot" role="status">
            <Show when={offline()}>
              <p class="banner">Can't reach the device. Retrying…</p>
            </Show>
          </div>
          {props.children}
        </main>
      </div>
    </StatusContext.Provider>
  );
}

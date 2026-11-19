import { createEffect, createSignal, For, onCleanup, onMount, Show } from "solid-js";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { deviceNow, getEvents, getHome, getLocation, offline, refreshLocation } from "./api";
import { placeName, ROOM_FRESH_SECONDS } from "./signs";
import { ago, clockTime, isoTime, plural, timeOfDay, useNow, usePoll, useTitle } from "./lib";

// Which room they are in, from the last sign the camera read, and today's moves.
function AtHome(props) {
  const home = usePoll(getHome, 5000);
  const events = usePoll(() => getEvents(200), 15000);
  const room = () => (home.data()?.room && home.data().room.name ? home.data().room : null);

  const startOfToday = () => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.getTime() / 1000 + (deviceNow() - Date.now() / 1000);
  };
  const moves = () =>
    (events.data() || []).filter((e) => e && e.kind === "room" && typeof e.at === "number" && e.at >= startOfToday()).slice(0, 8);

  const line = () => {
    const r = room();
    if (!r) return null;
    const since = Number.isFinite(r.since) ? ` since ${timeOfDay(r.since)}` : "";
    return `In ${placeName(r.name)}${since}`;
  };
  const stale = () => {
    const seen = room()?.seen_at;
    return Number.isFinite(seen) && props.now - seen > ROOM_FRESH_SECONDS;
  };

  return (
    <section class="at-home" aria-labelledby="at-home-heading">
      <h2 id="at-home-heading" class="h3">
        At home
      </h2>
      <Show when={home.loaded()} fallback={<p class="muted">{home.error() && !offline() ? `Couldn't check which room they're in. ${home.error().message}` : "Checking…"}</p>}>
        <Show
          when={room()}
          fallback={
            <p class="muted">
              No sign seen yet. Put up signs from the <a href="/home">Home page</a>.
            </p>
          }
        >
          <p class="at-home-room">{line()}</p>
          <Show when={stale()}>
            <p class="muted">The camera last read a sign {ago(room().seen_at, props.now)}.</p>
          </Show>
        </Show>
        <Show when={moves().length}>
          <h3 class="moves-heading">Today's room changes</h3>
          <ol class="moves">
            <For each={moves()}>
              {(e) => (
                <li>
                  <time datetime={isoTime(e.at)} title={clockTime(e.at)}>
                    {timeOfDay(e.at)}
                  </time>
                  <span>{e.text || "Moved room"}</span>
                </li>
              )}
            </For>
          </ol>
        </Show>
      </Show>
    </section>
  );
}

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function LocationMap(props) {
  let container;
  let map;
  let marker;
  let circle;
  let observer;

  let fitted = false;

  // Leaflet measures its box when it is created. Inside a <Show> the box can
  // still be detached or 0x0 at that moment, which leaves a blank grey map.
  // So start from a safe view, and fit the accuracy circle once the box has a
  // real size.
  function init() {
    if (map || !container) return;
    map = L.map(container, {
      zoomControl: true,
      scrollWheelZoom: false,
      // One-finger drags should scroll the page on phones, not pan the map.
      dragging: !L.Browser.mobile,
      attributionControl: true,
    }).setView([props.lat, props.lng], 13);
    map.attributionControl.setPrefix(false);
    const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors",
    });
    let failures = 0;
    tiles.on("tileerror", () => {
      failures += 1;
      if (failures >= 2) props.onTilesFailed?.(true);
    });
    tiles.on("tileload", () => {
      failures = 0;
      props.onTilesFailed?.(false);
    });
    tiles.addTo(map);

    const colour = cssVar("--moss", "#2F6B4F");
    circle = L.circle([props.lat, props.lng], {
      radius: props.accuracy > 0 ? props.accuracy : 1,
      color: colour,
      weight: 2,
      fillColor: colour,
      fillOpacity: 0.12,
      interactive: false,
    }).addTo(map);
    marker = L.circleMarker([props.lat, props.lng], {
      radius: 9,
      color: "#ffffff",
      weight: 3,
      fillColor: colour,
      fillOpacity: 1,
      interactive: false,
    }).addTo(map);

    observer = new ResizeObserver(() => {
      if (!map) return;
      map.invalidateSize();
      if (!fitted) fit();
    });
    observer.observe(container);
    fit();
  }

  onMount(() => requestAnimationFrame(init));

  function fit() {
    if (!map || !circle || !container || container.clientWidth === 0 || container.clientHeight === 0) return;
    map.invalidateSize();
    if (props.accuracy > 0) map.fitBounds(circle.getBounds(), { padding: [24, 24], maxZoom: 17 });
    else map.setView([props.lat, props.lng], 16);
    fitted = true;
  }

  createEffect(() => {
    const lat = props.lat;
    const lng = props.lng;
    const accuracy = props.accuracy;
    if (!map || !marker) return;
    marker.setLatLng([lat, lng]);
    circle.setLatLng([lat, lng]);
    circle.setRadius(accuracy > 0 ? accuracy : 1);
    fit();
  });

  onCleanup(() => {
    observer?.disconnect();
    map?.remove();
    map = undefined;
  });

  return (
    <div
      ref={container}
      class="map"
      role="region"
      aria-label="Map of the device's estimated position. The circle shows the area it is likely within."
    />
  );
}

function metres(m) {
  if (m >= 1000) return `${(m / 1000).toFixed(m >= 10000 ? 0 : 1)} km`;
  if (m >= 100) return `${Math.round(m / 10) * 10} m`;
  return `${Math.max(1, Math.round(m))} m`;
}

function widthKm(radius) {
  const km = (radius * 2) / 1000;
  if (km < 1) return `${(Math.round(km * 10) / 10).toFixed(1)} km`;
  return `${km < 10 ? km.toFixed(1) : Math.round(km)} km`;
}

export default function Place() {
  useTitle("Place");
  const now = useNow(10000);
  const location = usePoll(getLocation, 60000);
  const [checking, setChecking] = createSignal(false);
  const [error, setError] = createSignal("");
  const [tilesFailed, setTilesFailed] = createSignal(false);

  const data = () => location.data();
  const hasFix = () => {
    const d = data();
    return !!d && Number.isFinite(d.lat) && Number.isFinite(d.lng);
  };
  const accuracy = () => (Number.isFinite(data()?.accuracy) && data().accuracy > 0 ? data().accuracy : 0);

  async function checkAgain() {
    setChecking(true);
    setError("");
    try {
      const fresh = await refreshLocation();
      location.mutate(fresh);
    } catch (err) {
      setError(`Couldn't check the location. ${err.message}`);
    } finally {
      setChecking(false);
    }
  }

  const summary = () => {
    const d = data();
    if (!d || d.status !== "ok") return null;
    if (d.source === "wifi") {
      const n = Number.isFinite(d.access_points) ? d.access_points : null;
      const from = n === null ? "nearby Wi-Fi access points" : plural(n, "nearby Wi-Fi access point");
      return `Placed from ${from}, within about ${metres(accuracy())}.`;
    }
    if (Number.isFinite(d.access_points) && d.access_points >= 2) {
      return `Google could not match the ${d.access_points} nearby Wi-Fi access points, so it placed the device from its internet connection. This is a rough area, about ${widthKm(
        accuracy(),
      )} wide.`;
    }
    return `Only the internet connection's location was available, so this is a rough area, about ${widthKm(
      accuracy(),
    )} wide. Google needs at least two Wi-Fi access points in range for a closer fix.`;
  };

  const osmLink = () => {
    const d = data();
    return `https://www.openstreetmap.org/?mlat=${d.lat}&mlon=${d.lng}#map=16/${d.lat}/${d.lng}`;
  };

  return (
    <div class="page place">
      <div class="page-head">
        <h1 tabindex="-1">Place</h1>
        <p class="lede">Where they are: the room at home, and the device's position on the map.</p>
      </div>

      <AtHome now={now()} />

      <div class="map-head">
        <h2 class="h3">On the map</h2>
        <button type="button" class="button" onClick={checkAgain} disabled={checking() || offline()}>
          {checking() ? "Checking…" : "Check again"}
        </button>
      </div>

      <p role="alert" class="error-text">
        {error()}
      </p>

      <Show when={!location.loaded()}>
        <Show
          when={location.error() && !offline()}
          fallback={<p class="muted">{offline() ? "Waiting for the device." : "Looking up the location…"}</p>}
        >
          <p class="error-text" role="alert">
            Couldn't get the location. {location.error().message}
          </p>
        </Show>
      </Show>

      <Show when={data()?.status === "not_configured"}>
        <section class="panel setup">
          <h2>Location isn't set up yet</h2>
          <p>
            CogniSight uses Google's Geolocation service to place the device from nearby Wi-Fi networks. It needs a
            Google Geolocation API key.
          </p>
          <ol class="steps">
            <li>
              On the Pi, open the <code>.env</code> file in the CogniSight folder.
            </li>
            <li>
              Add a line: <code>GEOLOCATION_API_KEY=your-key</code>
            </li>
            <li>Restart CogniSight, then press “Check again”.</li>
          </ol>
        </section>
      </Show>

      <Show when={data()?.status === "error"}>
        <p class="note-attention" role="alert">
          The last location check failed. {data().error || "The lookup service didn't answer."} Press “Check again” to
          retry.
        </p>
      </Show>

      <Show when={hasFix()}>
        <div class="place-grid">
          <div class="map-frame">
            <LocationMap lat={data().lat} lng={data().lng} accuracy={accuracy()} onTilesFailed={setTilesFailed} />
            <Show when={tilesFailed()}>
              <p class="map-offline" role="status">
                The map can't load without an internet connection. The position below is still correct.
              </p>
            </Show>
          </div>
          <div class="place-facts">
            <Show when={summary()}>
              <p class="place-summary" classList={{ approximate: data().source !== "wifi" }}>
                {summary()}
              </p>
            </Show>
            <dl class="facts">
              <div>
                <dt>Coordinates</dt>
                <dd class="coords">
                  {data().lat.toFixed(5)}, {data().lng.toFixed(5)}
                </dd>
              </div>
              <Show when={accuracy()}>
                <div>
                  <dt>Accuracy</dt>
                  <dd>Within {metres(accuracy())}</dd>
                </div>
              </Show>
              <Show when={Number.isFinite(data().checked_at)}>
                <div>
                  <dt>Checked</dt>
                  <dd>
                    <span title={clockTime(data().checked_at)}>{capitalFirst(ago(data().checked_at, now()))}</span>
                  </dd>
                </div>
              </Show>
            </dl>
            <a class="text-link" href={osmLink()} target="_blank" rel="noopener noreferrer">
              Open in OpenStreetMap
            </a>
          </div>
        </div>
      </Show>
    </div>
  );
}

function capitalFirst(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

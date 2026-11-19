import { render } from "solid-js/web";
import { Route, Router } from "@solidjs/router";
import "@fontsource-variable/atkinson-hyperlegible-next";
import "./styles.css";
import Layout from "./App";
import Live from "./Live";
import People from "./People";
import Person from "./Person";
import Home from "./Home";
import Sign from "./Sign";
import PrintSigns from "./PrintSigns";
import Place from "./Place";
import Device from "./Device";
import { useTitle } from "./lib";

function NotFound() {
  useTitle("Page not found");
  return (
    <div class="page">
      <div class="empty">
        <h1 tabindex="-1">There's no page here</h1>
        <p class="muted">The link may be out of date.</p>
        <a class="button primary" href="/">
          Go to Live
        </a>
      </div>
    </div>
  );
}

render(
  () => (
    <Router root={Layout}>
      <Route path="/" component={Live} />
      <Route path="/people" component={People} />
      <Route path="/people/:name" component={Person} />
      <Route path="/home" component={Home} />
      <Route path="/home/signs/:id" component={Sign} />
      <Route path="/home/print" component={PrintSigns} />
      <Route path="/place" component={Place} />
      <Route path="/device" component={Device} />
      <Route path="*" component={NotFound} />
    </Router>
  ),
  document.getElementById("root"),
);

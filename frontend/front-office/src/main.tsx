/**
 * Entry point of the front office (customer portal + advisor desk). It loads the fonts and the shared styles,
 * then mounts the React app into the <div id="root"> of index.html.
 */
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/space-grotesk";
import "@callverse/shared/styles.css";
import { MotionConfig, MotionGlobalConfig } from "framer-motion";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

// ?snapshot renders every animation in its final state (screenshots for the report, CI checks).
if (new URLSearchParams(window.location.search).has("snapshot")) MotionGlobalConfig.skipAnimations = true;

// StrictMode: extra checks in development. MotionConfig reducedMotion="user": follow the system's reduce-
// motion setting. BrowserRouter: pages change without reloading (the URL path picks the page).
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </MotionConfig>
  </React.StrictMode>,
);

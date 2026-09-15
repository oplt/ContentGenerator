import React from "react";
import ReactDOM from "react-dom/client";
// Critical weights only on first paint; 500/800 remain available via CSS if needed later.
import "@fontsource/manrope/400.css";
import "@fontsource/manrope/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "./index.css";
import { AppProviders } from "./app/providers";
import { AppRouter } from "./app/router";
import { initWebVitals } from "./telemetry/webVitals";

initWebVitals();

ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
        <AppProviders>
            <AppRouter />
        </AppProviders>
    </React.StrictMode>
);

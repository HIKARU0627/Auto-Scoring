import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { MaterialWindowApp } from "./features/materials/MaterialWindowPage";
import { ThemeProvider } from "./theme/ThemeProvider";
import "./styles/index.css";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("index.html must contain #root");
}

/**
 * The material window loads this same bundle with `?window=material`
 * (`main.ts`). The query string, not a second HTML entry, is what keeps the
 * second window on the identical CSP and preload (Issue #415 decision 2).
 */
const isMaterialWindow =
  new URLSearchParams(window.location.search).get("window") === "material";

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      {isMaterialWindow ? <MaterialWindowApp /> : <App />}
    </ThemeProvider>
  </StrictMode>,
);

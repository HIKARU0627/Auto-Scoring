import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ThemeProvider } from "./theme/ThemeProvider";
import "./styles/index.css";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("index.html must contain #root");
}

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
);

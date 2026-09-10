export type ThemeMode = "light" | "dark";

const STORAGE_KEY = "auto-scoring-theme";

export function readStoredTheme(): ThemeMode | null {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return null;
}

/** Owner decision (#201): calm dark flat design is the default. */
export function resolveTheme(): ThemeMode {
  return readStoredTheme() ?? "dark";
}

export function applyTheme(mode: ThemeMode): void {
  document.documentElement.dataset["theme"] = mode;
  localStorage.setItem(STORAGE_KEY, mode);
}

export function toggleTheme(): ThemeMode {
  const next: ThemeMode = resolveTheme() === "dark" ? "light" : "dark";
  applyTheme(next);
  return next;
}

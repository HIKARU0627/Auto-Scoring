import type { JSX, ReactNode } from "react";

import { BackOrHomeButton } from "./BackOrHomeButton.js";

export function ShellScreen({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}): JSX.Element {
  return (
    <div className="min-h-screen bg-surface text-on-surface">
      <header className="flex items-center gap-md border-b border-outline-variant px-xl py-md">
        <BackOrHomeButton />
        <h1 className="text-title-large font-medium leading-ui">{title}</h1>
      </header>
      <main className="p-xl">{children}</main>
    </div>
  );
}

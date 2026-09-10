import { useState, type JSX } from "react";

import type { DependencyDagLayout } from "../../core/dependency-dag.js";

export interface DependencyDagPanelProps {
  readonly layout: DependencyDagLayout;
  readonly selectedQuestionId: string | null;
  readonly onQuestionSelected: (questionId: string) => void;
}

export function DependencyDagPanel({
  layout,
  selectedQuestionId,
  onQuestionSelected,
}: DependencyDagPanelProps): JSX.Element {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <section
      data-testid="dependency-dag-panel"
      className="flex flex-col gap-sm border border-outline-variant rounded-md p-md"
    >
      <header className="flex items-center justify-between gap-md">
        <p data-testid="dag-progress-summary" className="text-body-medium">
          {layout.progressSummary}
        </p>
        <button
          type="button"
          data-testid="dag-toggle-button"
          className="text-ui-label"
          onClick={() => {
            setCollapsed((value) => !value);
          }}
        >
          {collapsed ? "展開" : "畳む"}
        </button>
      </header>

      {layout.failures.map((failure) => (
        <div
          key={failure.openQuestionId}
          data-testid={`dag-failure-${failure.openQuestionId}`}
          className="flex flex-col gap-xs rounded-md border border-error/30 bg-error-container/20 p-sm"
        >
          <p
            data-testid={`dag-failure-headline-${failure.openQuestionId}`}
            className="text-body-medium font-medium"
          >
            {failure.headline}
          </p>
          <p className="text-body-small">{failure.guidance.cause}</p>
          <p
            data-testid={`dag-failure-next-${failure.openQuestionId}`}
            className="text-body-small"
          >
            {failure.guidance.nextStep}
          </p>
          <button
            type="button"
            data-testid={`dag-failure-open-${failure.openQuestionId}`}
            className="self-start rounded-md border border-outline px-md py-xs text-ui-label"
            onClick={() => {
              onQuestionSelected(failure.openQuestionId);
            }}
          >
            設問を開く
          </button>
        </div>
      ))}

      {!collapsed ? (
        <div className="flex flex-wrap gap-sm">
          {layout.nodes.map((node) => (
            <button
              key={node.question.id}
              type="button"
              data-testid={`dag-node-${node.question.id}`}
              className={`rounded-md border px-md py-sm text-left ${
                selectedQuestionId === node.question.id
                  ? "border-primary bg-primary-container/20"
                  : "border-outline-variant"
              }`}
              onClick={() => {
                onQuestionSelected(node.question.id);
              }}
            >
              <span className="block text-ui-label">
                問{node.question.label}
              </span>
              <span
                data-testid={`dag-node-status-${node.question.id}`}
                className="block text-body-small"
              >
                {node.statusLabel}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

import { useEffect, useMemo, useState, type JSX } from "react";

import type {
  DependencyEdgeModel,
  QuestionResponse,
} from "../../api/test-registration-data.js";
import {
  excludedPrerequisiteRequirements,
  scoringTargetsSaveRequirements,
  unmetRequirements,
} from "../../core/action-requirements.js";
import { DisabledActionReason } from "../intake/DisabledActionReason.js";
import {
  Caption,
  Card,
  CardHeading,
  StatusPill,
  primaryButtonClass,
  secondaryButtonClass,
} from "../ui/screen-ui.js";

/**
 * 採点する設問を選ぶ (Issue #449).
 *
 * Default is every question. Selection lives locally until 「保存」; the server
 * is the source of truth and the page reloads the whole snapshot after a save,
 * so this card is re-seeded from the server's flags whenever they change.
 *
 * 「全部外す」 is not allowed: the save button is disabled and
 * `action-requirements.ts` carries the reason. A scored question whose
 * prerequisite is excluded is not blocked either -- the dependent is graded
 * without the prerequisite's result, matching the OCR-unavailable path -- but
 * it is named here so that change is visible rather than silent.
 */
export function ScoringTargetsCard({
  questions,
  edges,
  busy,
  onSave,
}: {
  questions: readonly QuestionResponse[];
  edges: readonly DependencyEdgeModel[];
  busy: boolean;
  onSave: (questionIds: readonly string[]) => Promise<void>;
}): JSX.Element {
  const serverSelection = useMemo(
    () =>
      questions
        .filter((question) => question.is_scoring_target)
        .map((question) => question.id),
    [questions],
  );
  const [selected, setSelected] = useState<readonly string[]>(serverSelection);
  useEffect(() => {
    setSelected(serverSelection);
  }, [serverSelection]);

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const numberById = useMemo(
    () => new Map(questions.map((question) => [question.id, question.number])),
    [questions],
  );
  const dependentNumbers = useMemo(() => {
    const numbers: string[] = [];
    for (const edge of edges) {
      if (
        !selectedSet.has(edge.to_question_id) ||
        selectedSet.has(edge.from_question_id)
      ) {
        continue;
      }
      const number = numberById.get(edge.to_question_id);
      if (number !== undefined) {
        numbers.push(number);
      }
    }
    return [...new Set(numbers)];
  }, [edges, numberById, selectedSet]);

  const saveRequirements = scoringTargetsSaveRequirements({
    busy,
    selectedCount: selected.length,
  });
  const noticeRequirements = excludedPrerequisiteRequirements({
    dependentNumbers,
  });
  const dirty =
    selected.length !== serverSelection.length ||
    selected.some((id) => !serverSelection.includes(id));

  return (
    <Card testId="scoring-targets-section">
      <CardHeading
        title="採点する問題"
        description="採点する設問を選びます。既定はすべてです。登録完了の前でも後でも変更できます。"
        aside={
          <StatusPill tone="attention">
            {selected.length} / {questions.length} 問
          </StatusPill>
        }
      />
      {questions.length === 0 ? (
        <p
          data-testid="scoring-targets-empty"
          className="mt-md text-body-medium text-on-surface-variant"
        >
          まだ設問がありません。配点と採点基準を確定すると設問ができます。
        </p>
      ) : (
        <div className="mt-md flex flex-col gap-sm">
          {questions.map((question) => (
            <label key={question.id} className="flex items-center gap-sm">
              <input
                type="checkbox"
                data-testid={`scoring-target-${question.number}`}
                className="h-4 w-4"
                checked={selectedSet.has(question.id)}
                disabled={busy}
                onChange={() => {
                  setSelected((current) =>
                    current.includes(question.id)
                      ? current.filter((item) => item !== question.id)
                      : [...current, question.id],
                  );
                }}
              />
              <span className="text-body-medium text-on-surface">
                {question.number}（{question.points}点）
              </span>
            </label>
          ))}
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button
          type="button"
          data-testid="save-scoring-targets-button"
          className={primaryButtonClass()}
          disabled={saveRequirements.length > 0}
          onClick={() => {
            void onSave(selected);
          }}
        >
          採点する問題を保存
        </button>
        <button
          type="button"
          data-testid="select-all-scoring-targets-button"
          className={secondaryButtonClass()}
          disabled={busy || questions.length === 0}
          onClick={() => {
            setSelected(questions.map((question) => question.id));
          }}
        >
          すべて選ぶ
        </button>
      </div>
      {dirty ? (
        <div className="mt-sm">
          <Caption testId="scoring-targets-unsaved">
            変更はまだ保存されていません。
          </Caption>
        </div>
      ) : null}
      <DisabledActionReason
        requirements={unmetRequirements(saveRequirements)}
      />
      <DisabledActionReason requirements={noticeRequirements} />
    </Card>
  );
}

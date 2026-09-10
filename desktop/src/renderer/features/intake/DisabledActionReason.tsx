import type { JSX } from "react";

import type { ActionRequirement } from "../../core/action-requirements.js";

export function DisabledActionReason({
  requirements,
}: {
  requirements: readonly ActionRequirement[];
}): JSX.Element | null {
  if (requirements.length === 0) {
    return null;
  }
  return (
    <div className="mt-sm flex flex-col gap-xs">
      {requirements.map((requirement) => (
        <p
          key={requirement.id}
          data-testid={`disabled-reason-${requirement.id}`}
          className="text-body-medium text-on-surface-variant"
        >
          {requirement.message}
        </p>
      ))}
    </div>
  );
}

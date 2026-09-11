import type { JSX } from "react";

import type { ActionRequirement } from "../../core/action-requirements.js";

/**
 * 「何を満たせば有効になるか」を無効なボタンの隣に出す (INV-104〜106, INV-109,
 * Issue #272).
 *
 * **ツールチップではない。** ツールチップはポインタを当てた人にしか出ないので、
 * キーボードだけの人には届かない。ここは常にツリーに居る `<p>` で、Tab の順番も
 * 取らない。アイコンを添えて、色覚に頼らず状態を読めるようにしてある。
 *
 * 文言は持たない。判断の元になる `ActionRequirement` を並べるだけで、この
 * component は「何件あるとき、どう置くか」だけを決める。文言の方針は
 * `docs/frontend-invariants.md` §7。
 *
 * [requirements] が空のときは**何も描かない**。余白も取らない: 条件を満たした
 * 瞬間に理由が消えるのが、この component の振る舞いの半分である (残りの半分は、
 * 無効なら必ず1件以上あること -- `core/action-requirements.ts`)。
 */
export function DisabledActionReason({
  requirements,
}: {
  requirements: readonly ActionRequirement[];
}): JSX.Element | null {
  if (requirements.length === 0) {
    return null;
  }
  return (
    <div className="mt-sm flex items-start gap-sm">
      <span
        aria-hidden
        className="material-symbols-outlined shrink-0 text-body-medium text-on-surface-variant"
      >
        info_outline
      </span>
      {/* `min-w-0 flex-1`: without them the row cannot shrink below the text's
          intrinsic width and the reason runs off a 700px window instead of
          wrapping. `break-words` lets a long unbroken run wrap too. */}
      <div className="flex min-w-0 flex-1 flex-col gap-xs">
        {requirements.map((requirement) => (
          <p
            key={requirement.id}
            data-testid={`disabled-reason-${requirement.id}`}
            className="break-words text-body-medium text-on-surface-variant"
          >
            {requirement.message}
          </p>
        ))}
      </div>
    </div>
  );
}

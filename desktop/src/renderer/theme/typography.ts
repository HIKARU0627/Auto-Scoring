/**
 * Typography tokens and text roles for the Electron renderer (INV-083, INV-084, INV-085, INV-086).
 *
 * Single source of truth for text roles matching Flutter's `app_typography.dart`
 * and `docs/design-tokens.md` §2.
 */

export const APP_FONT_FAMILY = "Noto Sans JP";

export interface TextRoleStyle {
  readonly fontFamily: string;
  readonly fontSize: string;
  readonly lineHeight: number;
  readonly letterSpacing: string | number;
  readonly fontWeight: number;
  readonly fontVariantNumeric?: "tabular-nums" | "normal";
}

export interface AppTextRoles {
  readonly questionText: TextRoleStyle;
  readonly recognizedText: TextRoleStyle;
  readonly gradingComment: TextRoleStyle;
  readonly score: TextRoleStyle;
  readonly uiLabel: TextRoleStyle;
}

/**
 * Text role specifications.
 * - questionText: ordinary reading text, generous leading (1.75), bodyLarge size (16px)
 * - recognizedText: tuned for character-by-character comparison, larger (17px), positive tracking (0.5px)
 * - gradingComment: prose for student review, bodyMedium size (14px), generous leading (1.75), zero tracking
 * - score: headlineSmall (24px), tight leading (1.4), tabular-nums so digits do not jump on update
 * - uiLabel: labelLarge (14px), tight leading (1.4), zero tracking
 */
export const APP_TEXT_ROLES: AppTextRoles = {
  questionText: {
    fontFamily: APP_FONT_FAMILY,
    fontSize: "16px",
    lineHeight: 1.75,
    letterSpacing: "0px",
    fontWeight: 400,
  },
  recognizedText: {
    fontFamily: APP_FONT_FAMILY,
    fontSize: "17px",
    lineHeight: 1.75,
    letterSpacing: "0.5px",
    fontWeight: 400,
  },
  gradingComment: {
    fontFamily: APP_FONT_FAMILY,
    fontSize: "14px",
    lineHeight: 1.75,
    letterSpacing: "0px",
    fontWeight: 400,
  },
  score: {
    fontFamily: APP_FONT_FAMILY,
    fontSize: "24px",
    lineHeight: 1.4,
    letterSpacing: "0px",
    fontWeight: 500,
    fontVariantNumeric: "tabular-nums",
  },
  uiLabel: {
    fontFamily: APP_FONT_FAMILY,
    fontSize: "14px",
    lineHeight: 1.4,
    letterSpacing: "0px",
    fontWeight: 500,
  },
};

export type ConfidenceLevel = "high" | "medium" | "low";

const MEDIUM_THRESHOLD = 0.7;
const HIGH_THRESHOLD = 0.9;

export function confidenceLevelOf(confidence: number): ConfidenceLevel {
  if (confidence >= HIGH_THRESHOLD) {
    return "high";
  }
  if (confidence >= MEDIUM_THRESHOLD) {
    return "medium";
  }
  return "low";
}

export function confidenceLevelLabel(level: ConfidenceLevel): string {
  switch (level) {
    case "high":
      return "高";
    case "medium":
      return "中";
    case "low":
      return "低";
  }
}

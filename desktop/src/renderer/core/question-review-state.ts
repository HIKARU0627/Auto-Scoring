import type { components } from "../api/generated/schema.js";

export type GradeResultResponse = components["schemas"]["GradeResultResponse"];
export type ReviewResponse = components["schemas"]["ReviewResponse"];
export type AnnotationResponse = components["schemas"]["AnnotationResponse"];
export type RecognitionResponse = components["schemas"]["RecognitionResponse"];

function effectiveLatestReview(
  reviews: readonly ReviewResponse[],
): ReviewResponse | null {
  for (let i = reviews.length - 1; i >= 0; i -= 1) {
    const review = reviews[i];
    if (review != null && review.action !== "undone") {
      return review;
    }
  }
  return null;
}

export function displayGrade(
  grades: readonly GradeResultResponse[],
  reviews: readonly ReviewResponse[],
): GradeResultResponse | null {
  const review = effectiveLatestReview(reviews);
  if (review?.human_grade_result_id != null) {
    return (
      grades.find((g) => g.id === review.human_grade_result_id) ??
      grades.at(-1) ??
      null
    );
  }
  if (review?.ai_grade_result_id != null) {
    return grades.find((g) => g.id === review.ai_grade_result_id) ?? null;
  }
  return grades.at(-1) ?? null;
}

export function annotationsForDisplayedAttempt(
  annotations: readonly AnnotationResponse[],
  displayGrade: GradeResultResponse | null,
): AnnotationResponse[] {
  if (displayGrade == null) {
    return [];
  }
  const createdAt = displayGrade.created_at;
  return annotations.filter((a) => a.created_at === createdAt);
}

export function recognitionsForDisplayedAttempt(
  recognitions: readonly RecognitionResponse[],
  displayGrade: GradeResultResponse | null,
): RecognitionResponse[] {
  if (displayGrade == null) {
    return [];
  }
  const cutoff = displayGrade.created_at;
  return recognitions.filter((r) => r.created_at <= cutoff);
}

export function expectedReviewVersion(
  reviews: readonly ReviewResponse[],
): number {
  return reviews.length;
}

export function effectiveReview(
  reviews: readonly ReviewResponse[],
): ReviewResponse | null {
  return effectiveLatestReview(reviews);
}

export function isQuestionConfirmed(
  reviews: readonly ReviewResponse[],
): boolean {
  const action = effectiveLatestReview(reviews)?.action;
  return action === "approved" || action === "modified";
}

export function latestAiGrade(
  grades: readonly GradeResultResponse[],
): GradeResultResponse | null {
  for (let index = grades.length - 1; index >= 0; index -= 1) {
    const grade = grades[index];
    if (grade?.source === "ai") {
      return grade;
    }
  }
  return null;
}

export function latestOcrRecognition(
  recognitions: readonly RecognitionResponse[],
): RecognitionResponse | null {
  for (let index = recognitions.length - 1; index >= 0; index -= 1) {
    const recognition = recognitions[index];
    if (recognition?.stage === "ocr") {
      return recognition;
    }
  }
  return null;
}

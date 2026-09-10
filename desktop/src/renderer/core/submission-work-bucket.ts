/**
 * Collapses seven submission states into the five buckets home and the queue
 * count (`app/lib/core/submission_work_bucket.dart`).
 */
export const HomeWorkBucket = {
  needsReview: "needsReview",
  intakeDone: "intakeDone",
  processing: "processing",
  failed: "failed",
  done: "done",
} as const;

export type HomeWorkBucket =
  (typeof HomeWorkBucket)[keyof typeof HomeWorkBucket];

export interface HomeWorkBucketMeta {
  readonly label: string;
  readonly tone: "attention" | "neutral" | "danger" | "success";
}

const BUCKET_META: Record<HomeWorkBucket, HomeWorkBucketMeta> = {
  [HomeWorkBucket.needsReview]: { label: "要確認", tone: "attention" },
  [HomeWorkBucket.intakeDone]: { label: "取込済み", tone: "neutral" },
  [HomeWorkBucket.processing]: { label: "処理中", tone: "neutral" },
  [HomeWorkBucket.failed]: { label: "取込失敗", tone: "danger" },
  [HomeWorkBucket.done]: { label: "確認済み", tone: "success" },
};

export const HOME_WORK_BUCKET_ORDER: readonly HomeWorkBucket[] = [
  HomeWorkBucket.needsReview,
  HomeWorkBucket.intakeDone,
  HomeWorkBucket.processing,
  HomeWorkBucket.failed,
  HomeWorkBucket.done,
];

export function homeWorkBucketOf(submissionState: string): HomeWorkBucket {
  switch (submissionState) {
    case "needs_review":
      return HomeWorkBucket.needsReview;
    case "ai_processed":
      return HomeWorkBucket.intakeDone;
    case "unprocessed":
    case "ai_processing":
      return HomeWorkBucket.processing;
    case "error":
      return HomeWorkBucket.failed;
    case "reviewed":
    case "exported":
      return HomeWorkBucket.done;
    default:
      return HomeWorkBucket.processing;
  }
}

export function homeWorkBucketMeta(bucket: HomeWorkBucket): HomeWorkBucketMeta {
  return BUCKET_META[bucket];
}

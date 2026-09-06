import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for JobsApi
void main() {
  final instance = AutoScoringApi().getJobsApi();

  group(JobsApi, () {
    // Cancel Job
    //
    //Future<JobResponse> cancelJobJobsJobIdCancelPost(String jobId) async
    test('test cancelJobJobsJobIdCancelPost', () async {
      // TODO
    });

    // Create Submission Jobs
    //
    //Future<BuiltList<JobResponse>> createSubmissionJobsSubmissionsSubmissionIdJobsPost(String submissionId) async
    test('test createSubmissionJobsSubmissionsSubmissionIdJobsPost', () async {
      // TODO
    });

    // Get Job
    //
    //Future<JobResponse> getJobJobsJobIdGet(String jobId) async
    test('test getJobJobsJobIdGet', () async {
      // TODO
    });

    // List Submission Jobs
    //
    //Future<BuiltList<JobResponse>> listSubmissionJobsSubmissionsSubmissionIdJobsGet(String submissionId) async
    test('test listSubmissionJobsSubmissionsSubmissionIdJobsGet', () async {
      // TODO
    });

    // Resume Question
    //
    //Future resumeQuestionSubmissionsSubmissionIdQuestionsQuestionIdResumePost(String submissionId, String questionId) async
    test(
        'test resumeQuestionSubmissionsSubmissionIdQuestionsQuestionIdResumePost',
        () async {
      // TODO
    });

    // Retry Job
    //
    //Future<JobResponse> retryJobJobsJobIdRetryPost(String jobId) async
    test('test retryJobJobsJobIdRetryPost', () async {
      // TODO
    });
  });
}

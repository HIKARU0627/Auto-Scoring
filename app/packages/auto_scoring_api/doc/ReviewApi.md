# auto_scoring_api.api.ReviewApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**approveSubmissionsSubmissionIdQuestionsQuestionIdReviewApprovePost**](ReviewApi.md#approvesubmissionssubmissionidquestionsquestionidreviewapprovepost) | **POST** /submissions/{submission_id}/questions/{question_id}/review/approve | Approve
[**editSubmissionsSubmissionIdQuestionsQuestionIdReviewEditPost**](ReviewApi.md#editsubmissionssubmissionidquestionsquestionidrevieweditpost) | **POST** /submissions/{submission_id}/questions/{question_id}/review/edit | Edit
[**getSourcePdfSubmissionsSubmissionIdSourcePdfGet**](ReviewApi.md#getsourcepdfsubmissionssubmissionidsourcepdfget) | **GET** /submissions/{submission_id}/source-pdf | Get Source Pdf
[**gradeManuallySubmissionsSubmissionIdQuestionsQuestionIdReviewGradePost**](ReviewApi.md#grademanuallysubmissionssubmissionidquestionsquestionidreviewgradepost) | **POST** /submissions/{submission_id}/questions/{question_id}/review/grade | Grade Manually
[**listAnnotationsSubmissionsSubmissionIdQuestionsQuestionIdAnnotationsGet**](ReviewApi.md#listannotationssubmissionssubmissionidquestionsquestionidannotationsget) | **GET** /submissions/{submission_id}/questions/{question_id}/annotations | List Annotations
[**listGradesSubmissionsSubmissionIdQuestionsQuestionIdGradesGet**](ReviewApi.md#listgradessubmissionssubmissionidquestionsquestionidgradesget) | **GET** /submissions/{submission_id}/questions/{question_id}/grades | List Grades
[**listQuestionsTestsTestIdQuestionsGet**](ReviewApi.md#listquestionsteststestidquestionsget) | **GET** /tests/{test_id}/questions | List Questions
[**listReviewProgressTestsTestIdReviewProgressGet**](ReviewApi.md#listreviewprogressteststestidreviewprogressget) | **GET** /tests/{test_id}/review-progress | List Review Progress
[**listReviewsSubmissionsSubmissionIdQuestionsQuestionIdReviewsGet**](ReviewApi.md#listreviewssubmissionssubmissionidquestionsquestionidreviewsget) | **GET** /submissions/{submission_id}/questions/{question_id}/reviews | List Reviews
[**regradeSubmissionsSubmissionIdQuestionsQuestionIdReviewRegradePost**](ReviewApi.md#regradesubmissionssubmissionidquestionsquestionidreviewregradepost) | **POST** /submissions/{submission_id}/questions/{question_id}/review/regrade | Regrade
[**rejectSubmissionsSubmissionIdQuestionsQuestionIdReviewRejectPost**](ReviewApi.md#rejectsubmissionssubmissionidquestionsquestionidreviewrejectpost) | **POST** /submissions/{submission_id}/questions/{question_id}/review/reject | Reject
[**undoSubmissionsSubmissionIdQuestionsQuestionIdReviewUndoPost**](ReviewApi.md#undosubmissionssubmissionidquestionsquestionidreviewundopost) | **POST** /submissions/{submission_id}/questions/{question_id}/review/undo | Undo


# **approveSubmissionsSubmissionIdQuestionsQuestionIdReviewApprovePost**
> ReviewActionResponse approveSubmissionsSubmissionIdQuestionsQuestionIdReviewApprovePost(submissionId, questionId, approveReviewRequest)

Approve

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 
final ApproveReviewRequest approveReviewRequest = ; // ApproveReviewRequest | 

try {
    final response = api.approveSubmissionsSubmissionIdQuestionsQuestionIdReviewApprovePost(submissionId, questionId, approveReviewRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->approveSubmissionsSubmissionIdQuestionsQuestionIdReviewApprovePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 
 **approveReviewRequest** | [**ApproveReviewRequest**](ApproveReviewRequest.md)|  | 

### Return type

[**ReviewActionResponse**](ReviewActionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **editSubmissionsSubmissionIdQuestionsQuestionIdReviewEditPost**
> ReviewActionResponse editSubmissionsSubmissionIdQuestionsQuestionIdReviewEditPost(submissionId, questionId, editReviewRequest)

Edit

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 
final EditReviewRequest editReviewRequest = ; // EditReviewRequest | 

try {
    final response = api.editSubmissionsSubmissionIdQuestionsQuestionIdReviewEditPost(submissionId, questionId, editReviewRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->editSubmissionsSubmissionIdQuestionsQuestionIdReviewEditPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 
 **editReviewRequest** | [**EditReviewRequest**](EditReviewRequest.md)|  | 

### Return type

[**ReviewActionResponse**](ReviewActionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getSourcePdfSubmissionsSubmissionIdSourcePdfGet**
> Uint8List getSourcePdfSubmissionsSubmissionIdSourcePdfGet(submissionId)

Get Source Pdf

The original, unmodified answer PDF's raw bytes (§13.1: 元PDF自体は 直接編集しない).  **Used by the Flutter 添削レビュー screen until the Electron cut-over**, and by nothing else -- it renders the PDF itself with `pdfrx` and draws the annotation overlay on top.  The new UI does not receive raw PDF bytes. PoC 6 (`docs/poc-6-pdf-coordinates.md`) put the rasterization in the sidecar, so that the pdfium which draws the page is the same one that performs the coordinate transform; the Electron screen reads ``GET /submissions/{submission_id}/pages`` and ``.../pages/{page_index}/image`` (`api.page_image_router`) instead, and app-data stays owned by the sidecar.  **After the cut-over there is no known caller left** -- the export path opens the stored file directly rather than going through HTTP. **Whether to delete this endpoint (and ``GET /tests/{test_id}/answer-layout/pdf``, kept for the same reason) is decided at cut-over, tracked in Issue #201.**

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String submissionId = submissionId_example; // String | 

try {
    final response = api.getSourcePdfSubmissionsSubmissionIdSourcePdfGet(submissionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->getSourcePdfSubmissionsSubmissionIdSourcePdfGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 

### Return type

[**Uint8List**](Uint8List.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/pdf, application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **gradeManuallySubmissionsSubmissionIdQuestionsQuestionIdReviewGradePost**
> ReviewActionResponse gradeManuallySubmissionsSubmissionIdQuestionsQuestionIdReviewGradePost(submissionId, questionId, manualGradeRequest)

Grade Manually

Record a person's own grade for a question with no AI grade at all (Issue #118) -- the way out of a permanently-failed grading job, which by design leaves no `GradeResult` behind (Issue #97).  409 when an AI grade does exist: that is the ``edit``/``approve`` case, and this route must not quietly set aside an attempt the reviewer has not seen.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 
final ManualGradeRequest manualGradeRequest = ; // ManualGradeRequest | 

try {
    final response = api.gradeManuallySubmissionsSubmissionIdQuestionsQuestionIdReviewGradePost(submissionId, questionId, manualGradeRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->gradeManuallySubmissionsSubmissionIdQuestionsQuestionIdReviewGradePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 
 **manualGradeRequest** | [**ManualGradeRequest**](ManualGradeRequest.md)|  | 

### Return type

[**ReviewActionResponse**](ReviewActionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listAnnotationsSubmissionsSubmissionIdQuestionsQuestionIdAnnotationsGet**
> BuiltList<AnnotationResponse> listAnnotationsSubmissionsSubmissionIdQuestionsQuestionIdAnnotationsGet(submissionId, questionId)

List Annotations

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 

try {
    final response = api.listAnnotationsSubmissionsSubmissionIdQuestionsQuestionIdAnnotationsGet(submissionId, questionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->listAnnotationsSubmissionsSubmissionIdQuestionsQuestionIdAnnotationsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 

### Return type

[**BuiltList&lt;AnnotationResponse&gt;**](AnnotationResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listGradesSubmissionsSubmissionIdQuestionsQuestionIdGradesGet**
> BuiltList<GradeResultResponse> listGradesSubmissionsSubmissionIdQuestionsQuestionIdGradesGet(submissionId, questionId)

List Grades

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 

try {
    final response = api.listGradesSubmissionsSubmissionIdQuestionsQuestionIdGradesGet(submissionId, questionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->listGradesSubmissionsSubmissionIdQuestionsQuestionIdGradesGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 

### Return type

[**BuiltList&lt;GradeResultResponse&gt;**](GradeResultResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listQuestionsTestsTestIdQuestionsGet**
> BuiltList<QuestionResponse> listQuestionsTestsTestIdQuestionsGet(testId, includeExcludedQuestions)

List Questions

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String testId = testId_example; // String | 
final bool includeExcludedQuestions = true; // bool | Return every question, not only the grading targets. The review screen leaves this at the default so an excluded question is never shown as work to do (Issue #449); the test-settings screen sets it to list them for re-selection.

try {
    final response = api.listQuestionsTestsTestIdQuestionsGet(testId, includeExcludedQuestions);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->listQuestionsTestsTestIdQuestionsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **includeExcludedQuestions** | **bool**| Return every question, not only the grading targets. The review screen leaves this at the default so an excluded question is never shown as work to do (Issue #449); the test-settings screen sets it to list them for re-selection. | [optional] [default to false]

### Return type

[**BuiltList&lt;QuestionResponse&gt;**](QuestionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listReviewProgressTestsTestIdReviewProgressGet**
> BuiltList<SubmissionReviewProgressResponse> listReviewProgressTestsTestIdReviewProgressGet(testId)

List Review Progress

Per-question review progress for every answer of one test.  Ordered by the answers' own ``created_at``, the order every other list of a test's answers already uses (`SubmissionRepository.list_for_test`), so the client never has to re-sort to line this up with `GET /tests/{id}/submissions`.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String testId = testId_example; // String | 

try {
    final response = api.listReviewProgressTestsTestIdReviewProgressGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->listReviewProgressTestsTestIdReviewProgressGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**BuiltList&lt;SubmissionReviewProgressResponse&gt;**](SubmissionReviewProgressResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listReviewsSubmissionsSubmissionIdQuestionsQuestionIdReviewsGet**
> BuiltList<ReviewResponse> listReviewsSubmissionsSubmissionIdQuestionsQuestionIdReviewsGet(submissionId, questionId)

List Reviews

The full append-only operation history, oldest first. Its length is the ``expected_version`` the client's *next* mutating call for this submission-question must pass (0 if the list is empty).

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 

try {
    final response = api.listReviewsSubmissionsSubmissionIdQuestionsQuestionIdReviewsGet(submissionId, questionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->listReviewsSubmissionsSubmissionIdQuestionsQuestionIdReviewsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 

### Return type

[**BuiltList&lt;ReviewResponse&gt;**](ReviewResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **regradeSubmissionsSubmissionIdQuestionsQuestionIdReviewRegradePost**
> ReviewActionResponse regradeSubmissionsSubmissionIdQuestionsQuestionIdReviewRegradePost(submissionId, questionId, reasonedReviewRequest)

Regrade

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 
final ReasonedReviewRequest reasonedReviewRequest = ; // ReasonedReviewRequest | 

try {
    final response = api.regradeSubmissionsSubmissionIdQuestionsQuestionIdReviewRegradePost(submissionId, questionId, reasonedReviewRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->regradeSubmissionsSubmissionIdQuestionsQuestionIdReviewRegradePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 
 **reasonedReviewRequest** | [**ReasonedReviewRequest**](ReasonedReviewRequest.md)|  | 

### Return type

[**ReviewActionResponse**](ReviewActionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **rejectSubmissionsSubmissionIdQuestionsQuestionIdReviewRejectPost**
> ReviewActionResponse rejectSubmissionsSubmissionIdQuestionsQuestionIdReviewRejectPost(submissionId, questionId, reasonedReviewRequest)

Reject

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 
final ReasonedReviewRequest reasonedReviewRequest = ; // ReasonedReviewRequest | 

try {
    final response = api.rejectSubmissionsSubmissionIdQuestionsQuestionIdReviewRejectPost(submissionId, questionId, reasonedReviewRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->rejectSubmissionsSubmissionIdQuestionsQuestionIdReviewRejectPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 
 **reasonedReviewRequest** | [**ReasonedReviewRequest**](ReasonedReviewRequest.md)|  | 

### Return type

[**ReviewActionResponse**](ReviewActionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **undoSubmissionsSubmissionIdQuestionsQuestionIdReviewUndoPost**
> ReviewActionResponse undoSubmissionsSubmissionIdQuestionsQuestionIdReviewUndoPost(submissionId, questionId, undoReviewRequest)

Undo

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 
final UndoReviewRequest undoReviewRequest = ; // UndoReviewRequest | 

try {
    final response = api.undoSubmissionsSubmissionIdQuestionsQuestionIdReviewUndoPost(submissionId, questionId, undoReviewRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->undoSubmissionsSubmissionIdQuestionsQuestionIdReviewUndoPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 
 **undoReviewRequest** | [**UndoReviewRequest**](UndoReviewRequest.md)|  | 

### Return type

[**ReviewActionResponse**](ReviewActionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)


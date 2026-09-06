# auto_scoring_api.api.ReviewApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getSourcePdfSubmissionsSubmissionIdSourcePdfGet**](ReviewApi.md#getsourcepdfsubmissionssubmissionidsourcepdfget) | **GET** /submissions/{submission_id}/source-pdf | Get Source Pdf
[**listAnnotationsSubmissionsSubmissionIdQuestionsQuestionIdAnnotationsGet**](ReviewApi.md#listannotationssubmissionssubmissionidquestionsquestionidannotationsget) | **GET** /submissions/{submission_id}/questions/{question_id}/annotations | List Annotations
[**listGradesSubmissionsSubmissionIdQuestionsQuestionIdGradesGet**](ReviewApi.md#listgradessubmissionssubmissionidquestionsquestionidgradesget) | **GET** /submissions/{submission_id}/questions/{question_id}/grades | List Grades
[**listQuestionsTestsTestIdQuestionsGet**](ReviewApi.md#listquestionsteststestidquestionsget) | **GET** /tests/{test_id}/questions | List Questions


# **getSourcePdfSubmissionsSubmissionIdSourcePdfGet**
> Uint8List getSourcePdfSubmissionsSubmissionIdSourcePdfGet(submissionId)

Get Source Pdf

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
> BuiltList<QuestionResponse> listQuestionsTestsTestIdQuestionsGet(testId)

List Questions

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getReviewApi();
final String testId = testId_example; // String | 

try {
    final response = api.listQuestionsTestsTestIdQuestionsGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ReviewApi->listQuestionsTestsTestIdQuestionsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**BuiltList&lt;QuestionResponse&gt;**](QuestionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)


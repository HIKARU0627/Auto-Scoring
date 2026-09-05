# auto_scoring_api.api.JobsApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**cancelJobJobsJobIdCancelPost**](JobsApi.md#canceljobjobsjobidcancelpost) | **POST** /jobs/{job_id}/cancel | Cancel Job
[**createSubmissionJobsSubmissionsSubmissionIdJobsPost**](JobsApi.md#createsubmissionjobssubmissionssubmissionidjobspost) | **POST** /submissions/{submission_id}/jobs | Create Submission Jobs
[**getJobJobsJobIdGet**](JobsApi.md#getjobjobsjobidget) | **GET** /jobs/{job_id} | Get Job
[**listSubmissionJobsSubmissionsSubmissionIdJobsGet**](JobsApi.md#listsubmissionjobssubmissionssubmissionidjobsget) | **GET** /submissions/{submission_id}/jobs | List Submission Jobs
[**resumeQuestionSubmissionsSubmissionIdQuestionsQuestionIdResumePost**](JobsApi.md#resumequestionsubmissionssubmissionidquestionsquestionidresumepost) | **POST** /submissions/{submission_id}/questions/{question_id}/resume | Resume Question
[**retryJobJobsJobIdRetryPost**](JobsApi.md#retryjobjobsjobidretrypost) | **POST** /jobs/{job_id}/retry | Retry Job


# **cancelJobJobsJobIdCancelPost**
> JobResponse cancelJobJobsJobIdCancelPost(jobId)

Cancel Job

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getJobsApi();
final String jobId = jobId_example; // String | 

try {
    final response = api.cancelJobJobsJobIdCancelPost(jobId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling JobsApi->cancelJobJobsJobIdCancelPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

[**JobResponse**](JobResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createSubmissionJobsSubmissionsSubmissionIdJobsPost**
> BuiltList<JobResponse> createSubmissionJobsSubmissionsSubmissionIdJobsPost(submissionId)

Create Submission Jobs

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getJobsApi();
final String submissionId = submissionId_example; // String | 

try {
    final response = api.createSubmissionJobsSubmissionsSubmissionIdJobsPost(submissionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling JobsApi->createSubmissionJobsSubmissionsSubmissionIdJobsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 

### Return type

[**BuiltList&lt;JobResponse&gt;**](JobResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getJobJobsJobIdGet**
> JobResponse getJobJobsJobIdGet(jobId)

Get Job

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getJobsApi();
final String jobId = jobId_example; // String | 

try {
    final response = api.getJobJobsJobIdGet(jobId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling JobsApi->getJobJobsJobIdGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

[**JobResponse**](JobResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listSubmissionJobsSubmissionsSubmissionIdJobsGet**
> BuiltList<JobResponse> listSubmissionJobsSubmissionsSubmissionIdJobsGet(submissionId)

List Submission Jobs

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getJobsApi();
final String submissionId = submissionId_example; // String | 

try {
    final response = api.listSubmissionJobsSubmissionsSubmissionIdJobsGet(submissionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling JobsApi->listSubmissionJobsSubmissionsSubmissionIdJobsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 

### Return type

[**BuiltList&lt;JobResponse&gt;**](JobResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **resumeQuestionSubmissionsSubmissionIdQuestionsQuestionIdResumePost**
> resumeQuestionSubmissionsSubmissionIdQuestionsQuestionIdResumePost(submissionId, questionId)

Resume Question

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getJobsApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 

try {
    api.resumeQuestionSubmissionsSubmissionIdQuestionsQuestionIdResumePost(submissionId, questionId);
} on DioException catch (e) {
    print('Exception when calling JobsApi->resumeQuestionSubmissionsSubmissionIdQuestionsQuestionIdResumePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 

### Return type

void (empty response body)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **retryJobJobsJobIdRetryPost**
> JobResponse retryJobJobsJobIdRetryPost(jobId)

Retry Job

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getJobsApi();
final String jobId = jobId_example; // String | 

try {
    final response = api.retryJobJobsJobIdRetryPost(jobId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling JobsApi->retryJobJobsJobIdRetryPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **jobId** | **String**|  | 

### Return type

[**JobResponse**](JobResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)


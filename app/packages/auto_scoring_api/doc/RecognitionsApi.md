# auto_scoring_api.api.RecognitionsApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**createManualRecognitionSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsPost**](RecognitionsApi.md#createmanualrecognitionsubmissionssubmissionidquestionsquestionidrecognitionspost) | **POST** /submissions/{submission_id}/questions/{question_id}/recognitions | Create Manual Recognition
[**getAnswerImageSubmissionsSubmissionIdQuestionsQuestionIdAnswerImageGet**](RecognitionsApi.md#getanswerimagesubmissionssubmissionidquestionsquestionidanswerimageget) | **GET** /submissions/{submission_id}/questions/{question_id}/answer-image | Get Answer Image
[**listRecognitionsSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsGet**](RecognitionsApi.md#listrecognitionssubmissionssubmissionidquestionsquestionidrecognitionsget) | **GET** /submissions/{submission_id}/questions/{question_id}/recognitions | List Recognitions


# **createManualRecognitionSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsPost**
> RecognitionResponse createManualRecognitionSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsPost(submissionId, questionId, manualRecognitionRequest)

Create Manual Recognition

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getRecognitionsApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 
final ManualRecognitionRequest manualRecognitionRequest = ; // ManualRecognitionRequest | 

try {
    final response = api.createManualRecognitionSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsPost(submissionId, questionId, manualRecognitionRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling RecognitionsApi->createManualRecognitionSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 
 **manualRecognitionRequest** | [**ManualRecognitionRequest**](ManualRecognitionRequest.md)|  | 

### Return type

[**RecognitionResponse**](RecognitionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getAnswerImageSubmissionsSubmissionIdQuestionsQuestionIdAnswerImageGet**
> JsonObject getAnswerImageSubmissionsSubmissionIdQuestionsQuestionIdAnswerImageGet(submissionId, questionId)

Get Answer Image

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getRecognitionsApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 

try {
    final response = api.getAnswerImageSubmissionsSubmissionIdQuestionsQuestionIdAnswerImageGet(submissionId, questionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling RecognitionsApi->getAnswerImageSubmissionsSubmissionIdQuestionsQuestionIdAnswerImageGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 

### Return type

[**JsonObject**](JsonObject.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listRecognitionsSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsGet**
> BuiltList<RecognitionResponse> listRecognitionsSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsGet(submissionId, questionId)

List Recognitions

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getRecognitionsApi();
final String submissionId = submissionId_example; // String | 
final String questionId = questionId_example; // String | 

try {
    final response = api.listRecognitionsSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsGet(submissionId, questionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling RecognitionsApi->listRecognitionsSubmissionsSubmissionIdQuestionsQuestionIdRecognitionsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **questionId** | **String**|  | 

### Return type

[**BuiltList&lt;RecognitionResponse&gt;**](RecognitionResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)


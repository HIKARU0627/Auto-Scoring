# auto_scoring_api.api.ExportApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**listExportsSubmissionsSubmissionIdExportsGet**](ExportApi.md#listexportssubmissionssubmissionidexportsget) | **GET** /submissions/{submission_id}/exports | List Exports
[**requestExportSubmissionsSubmissionIdExportPost**](ExportApi.md#requestexportsubmissionssubmissionidexportpost) | **POST** /submissions/{submission_id}/export | Request Export


# **listExportsSubmissionsSubmissionIdExportsGet**
> BuiltList<ExportResponse> listExportsSubmissionsSubmissionIdExportsGet(submissionId)

List Exports

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getExportApi();
final String submissionId = submissionId_example; // String | 

try {
    final response = api.listExportsSubmissionsSubmissionIdExportsGet(submissionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ExportApi->listExportsSubmissionsSubmissionIdExportsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 

### Return type

[**BuiltList&lt;ExportResponse&gt;**](ExportResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **requestExportSubmissionsSubmissionIdExportPost**
> ExportRequestResponse requestExportSubmissionsSubmissionIdExportPost(submissionId)

Request Export

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getExportApi();
final String submissionId = submissionId_example; // String | 

try {
    final response = api.requestExportSubmissionsSubmissionIdExportPost(submissionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ExportApi->requestExportSubmissionsSubmissionIdExportPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 

### Return type

[**ExportRequestResponse**](ExportRequestResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)


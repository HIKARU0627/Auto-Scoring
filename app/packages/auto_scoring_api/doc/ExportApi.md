# auto_scoring_api.api.ExportApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getExportFileExportsExportIdFileGet**](ExportApi.md#getexportfileexportsexportidfileget) | **GET** /exports/{export_id}/file | Get Export File
[**listExportsSubmissionsSubmissionIdExportsGet**](ExportApi.md#listexportssubmissionssubmissionidexportsget) | **GET** /submissions/{submission_id}/exports | List Exports
[**requestBulkExportTestsTestIdExportPost**](ExportApi.md#requestbulkexportteststestidexportpost) | **POST** /tests/{test_id}/export | Request Bulk Export
[**requestExportSubmissionsSubmissionIdExportPost**](ExportApi.md#requestexportsubmissionssubmissionidexportpost) | **POST** /submissions/{submission_id}/export | Request Export


# **getExportFileExportsExportIdFileGet**
> Uint8List getExportFileExportsExportIdFileGet(exportId)

Get Export File

The produced PDF itself, so the app can write it wherever the reviewer asked (Issue #142).  The sidecar does not copy files out of ``app-data/`` on request: the destination is a folder a human picked in a desktop file dialog, and `LocalFileStore` exists precisely to guarantee nothing the sidecar writes lands outside its own root. Handing over bytes keeps the \"where do the reviewer's files go\" decision entirely on the app side, where the dialog is, and mirrors how the review screen already gets `GET /submissions/{id}/source-pdf`.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getExportApi();
final String exportId = exportId_example; // String | 

try {
    final response = api.getExportFileExportsExportIdFileGet(exportId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ExportApi->getExportFileExportsExportIdFileGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **exportId** | **String**|  | 

### Return type

[**Uint8List**](Uint8List.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/pdf, application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

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

# **requestBulkExportTestsTestIdExportPost**
> BulkExportResponse requestBulkExportTestsTestIdExportPost(testId, bulkExportRequest)

Request Bulk Export

Export a whole test's answer sheets in one go (Issue #142).  Runs the *same* per-submission gate and re-export decision as ``POST /submissions/{id}/export`` -- `domain.pdf_export.export_refusal` and `decide_reexport` -- for every target, and **never raises on a per-submission outcome**. A reviewer running 40 answer sheets loses nothing to one unconfirmed sheet; the refused ones come back as rows to show, and the rest are queued.  All the `Job` rows are committed in one transaction and only then handed to the queue, matching the single endpoint's order (commit first, enqueue after) -- a queued id must always name a row that is actually there.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getExportApi();
final String testId = testId_example; // String | 
final BulkExportRequest bulkExportRequest = ; // BulkExportRequest | 

try {
    final response = api.requestBulkExportTestsTestIdExportPost(testId, bulkExportRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling ExportApi->requestBulkExportTestsTestIdExportPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **bulkExportRequest** | [**BulkExportRequest**](BulkExportRequest.md)|  | [optional] 

### Return type

[**BulkExportResponse**](BulkExportResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
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


# auto_scoring_api.api.PagesApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**getAnswerLayoutPageImageTestsTestIdAnswerLayoutPagesPageIndexImageGet**](PagesApi.md#getanswerlayoutpageimageteststestidanswerlayoutpagespageindeximageget) | **GET** /tests/{test_id}/answer-layout/pages/{page_index}/image | Get Answer Layout Page Image
[**getSubmissionPageImageSubmissionsSubmissionIdPagesPageIndexImageGet**](PagesApi.md#getsubmissionpageimagesubmissionssubmissionidpagespageindeximageget) | **GET** /submissions/{submission_id}/pages/{page_index}/image | Get Submission Page Image
[**listAnswerLayoutPagesTestsTestIdAnswerLayoutPagesGet**](PagesApi.md#listanswerlayoutpagesteststestidanswerlayoutpagesget) | **GET** /tests/{test_id}/answer-layout/pages | List Answer Layout Pages
[**listSubmissionPagesSubmissionsSubmissionIdPagesGet**](PagesApi.md#listsubmissionpagessubmissionssubmissionidpagesget) | **GET** /submissions/{submission_id}/pages | List Submission Pages


# **getAnswerLayoutPageImageTestsTestIdAnswerLayoutPagesPageIndexImageGet**
> Uint8List getAnswerLayoutPageImageTestsTestIdAnswerLayoutPagesPageIndexImageGet(testId, pageIndex, scale)

Get Answer Layout Page Image

One page of the test's answer sheet, rasterized by the same pdfium that performs the coordinate transform (PoC 6, approach B).  **A normalized coordinate is built from the returned image's own pixel size, and from nothing else** (`normalized_x = click_px / image_width_px`). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar's coordinate transform.  Do **not** divide by the `displayed_width` / `displayed_height` reported by `GET .../pages`. The image's pixel size is rounded up independently (`ceil(displayed x scale)`), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getPagesApi();
final String testId = testId_example; // String | 
final int pageIndex = 56; // int | 0-based page index.
final num scale = 8.14; // num | Pixels per PDF point. Only 1.0, 2.0 and 3.5 are accepted; any other value is rejected with 422 rather than snapped to a permitted one.

try {
    final response = api.getAnswerLayoutPageImageTestsTestIdAnswerLayoutPagesPageIndexImageGet(testId, pageIndex, scale);
    print(response);
} on DioException catch (e) {
    print('Exception when calling PagesApi->getAnswerLayoutPageImageTestsTestIdAnswerLayoutPagesPageIndexImageGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **pageIndex** | **int**| 0-based page index. | 
 **scale** | **num**| Pixels per PDF point. Only 1.0, 2.0 and 3.5 are accepted; any other value is rejected with 422 rather than snapped to a permitted one. | [optional] [default to 2.0]

### Return type

[**Uint8List**](Uint8List.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: image/png, application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getSubmissionPageImageSubmissionsSubmissionIdPagesPageIndexImageGet**
> Uint8List getSubmissionPageImageSubmissionsSubmissionIdPagesPageIndexImageGet(submissionId, pageIndex, scale)

Get Submission Page Image

One page of the answer PDF, rasterized by the same pdfium that performs the coordinate transform (PoC 6, approach B).  **A normalized coordinate is built from the returned image's own pixel size, and from nothing else** (`normalized_x = click_px / image_width_px`). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar's coordinate transform.  Do **not** divide by the `displayed_width` / `displayed_height` reported by `GET .../pages`. The image's pixel size is rounded up independently (`ceil(displayed x scale)`), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getPagesApi();
final String submissionId = submissionId_example; // String | 
final int pageIndex = 56; // int | 0-based page index.
final num scale = 8.14; // num | Pixels per PDF point. Only 1.0, 2.0 and 3.5 are accepted; any other value is rejected with 422 rather than snapped to a permitted one.

try {
    final response = api.getSubmissionPageImageSubmissionsSubmissionIdPagesPageIndexImageGet(submissionId, pageIndex, scale);
    print(response);
} on DioException catch (e) {
    print('Exception when calling PagesApi->getSubmissionPageImageSubmissionsSubmissionIdPagesPageIndexImageGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 
 **pageIndex** | **int**| 0-based page index. | 
 **scale** | **num**| Pixels per PDF point. Only 1.0, 2.0 and 3.5 are accepted; any other value is rejected with 422 rather than snapped to a permitted one. | [optional] [default to 2.0]

### Return type

[**Uint8List**](Uint8List.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: image/png, application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listAnswerLayoutPagesTestsTestIdAnswerLayoutPagesGet**
> DocumentPagesResponse listAnswerLayoutPagesTestsTestIdAnswerLayoutPagesGet(testId)

List Answer Layout Pages

Page count, displayed size and rotation of the test's answer sheet, for laying the answer-area editor out **before** the page images arrive, and for paging.  **A normalized coordinate is built from the returned image's own pixel size, and from nothing else** (`normalized_x = click_px / image_width_px`). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar's coordinate transform.  Do **not** divide by the `displayed_width` / `displayed_height` reported by `GET .../pages`. The image's pixel size is rounded up independently (`ceil(displayed x scale)`), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getPagesApi();
final String testId = testId_example; // String | 

try {
    final response = api.listAnswerLayoutPagesTestsTestIdAnswerLayoutPagesGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling PagesApi->listAnswerLayoutPagesTestsTestIdAnswerLayoutPagesGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**DocumentPagesResponse**](DocumentPagesResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listSubmissionPagesSubmissionsSubmissionIdPagesGet**
> DocumentPagesResponse listSubmissionPagesSubmissionsSubmissionIdPagesGet(submissionId)

List Submission Pages

Page count, displayed size and rotation of the answer PDF, for laying the viewer out **before** the page images arrive, and for paging.  **A normalized coordinate is built from the returned image's own pixel size, and from nothing else** (`normalized_x = click_px / image_width_px`). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar's coordinate transform.  Do **not** divide by the `displayed_width` / `displayed_height` reported by `GET .../pages`. The image's pixel size is rounded up independently (`ceil(displayed x scale)`), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getPagesApi();
final String submissionId = submissionId_example; // String | 

try {
    final response = api.listSubmissionPagesSubmissionsSubmissionIdPagesGet(submissionId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling PagesApi->listSubmissionPagesSubmissionsSubmissionIdPagesGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **submissionId** | **String**|  | 

### Return type

[**DocumentPagesResponse**](DocumentPagesResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)


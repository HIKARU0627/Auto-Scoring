# auto_scoring_api.api.TestRegistrationApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**analyzeProfileTestsTestIdProfileAnalyzePost**](TestRegistrationApi.md#analyzeprofileteststestidprofileanalyzepost) | **POST** /tests/{test_id}/profile/analyze | Analyze Profile
[**completeRegistrationTestsTestIdCompleteRegistrationPost**](TestRegistrationApi.md#completeregistrationteststestidcompleteregistrationpost) | **POST** /tests/{test_id}/complete-registration | Complete Registration
[**confirmProfileTestsTestIdProfileConfirmPost**](TestRegistrationApi.md#confirmprofileteststestidprofileconfirmpost) | **POST** /tests/{test_id}/profile/confirm | Confirm Profile
[**createTestTestsPost**](TestRegistrationApi.md#createtesttestspost) | **POST** /tests | Create Test
[**detectAnswerAreasTestsTestIdAnswerLayoutDetectPost**](TestRegistrationApi.md#detectanswerareasteststestidanswerlayoutdetectpost) | **POST** /tests/{test_id}/answer-layout/detect | Detect Answer Areas
[**getAnswerLayoutPdfTestsTestIdAnswerLayoutPdfGet**](TestRegistrationApi.md#getanswerlayoutpdfteststestidanswerlayoutpdfget) | **GET** /tests/{test_id}/answer-layout/pdf | Get Answer Layout Pdf
[**getAnswerLayoutTestsTestIdAnswerLayoutGet**](TestRegistrationApi.md#getanswerlayoutteststestidanswerlayoutget) | **GET** /tests/{test_id}/answer-layout | Get Answer Layout
[**getProfileTestsTestIdProfileGet**](TestRegistrationApi.md#getprofileteststestidprofileget) | **GET** /tests/{test_id}/profile | Get Profile
[**getTestTestsTestIdGet**](TestRegistrationApi.md#gettestteststestidget) | **GET** /tests/{test_id} | Get Test
[**listTestRegistrationsTestRegistrationsGet**](TestRegistrationApi.md#listtestregistrationstestregistrationsget) | **GET** /test-registrations | List Test Registrations
[**updateProfileTestsTestIdProfilePut**](TestRegistrationApi.md#updateprofileteststestidprofileput) | **PUT** /tests/{test_id}/profile | Update Profile
[**uploadAnswerLayoutTestsTestIdAnswerLayoutPut**](TestRegistrationApi.md#uploadanswerlayoutteststestidanswerlayoutput) | **PUT** /tests/{test_id}/answer-layout | Upload Answer Layout


# **analyzeProfileTestsTestIdProfileAnalyzePost**
> ProfileResponse analyzeProfileTestsTestIdProfileAnalyzePost(testId)

Analyze Profile

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 

try {
    final response = api.analyzeProfileTestsTestIdProfileAnalyzePost(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->analyzeProfileTestsTestIdProfileAnalyzePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**ProfileResponse**](ProfileResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **completeRegistrationTestsTestIdCompleteRegistrationPost**
> CompleteRegistrationResponse completeRegistrationTestsTestIdCompleteRegistrationPost(testId)

Complete Registration

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 

try {
    final response = api.completeRegistrationTestsTestIdCompleteRegistrationPost(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->completeRegistrationTestsTestIdCompleteRegistrationPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**CompleteRegistrationResponse**](CompleteRegistrationResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **confirmProfileTestsTestIdProfileConfirmPost**
> ProfileResponse confirmProfileTestsTestIdProfileConfirmPost(testId, confirmProfileRequest)

Confirm Profile

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 
final ConfirmProfileRequest confirmProfileRequest = ; // ConfirmProfileRequest | 

try {
    final response = api.confirmProfileTestsTestIdProfileConfirmPost(testId, confirmProfileRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->confirmProfileTestsTestIdProfileConfirmPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **confirmProfileRequest** | [**ConfirmProfileRequest**](ConfirmProfileRequest.md)|  | 

### Return type

[**ProfileResponse**](ProfileResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createTestTestsPost**
> TestResponse createTestTestsPost(manual, modelAnswer, name, subject)

Create Test

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final MultipartFile manual = BINARY_DATA_HERE; // MultipartFile | 
final MultipartFile modelAnswer = BINARY_DATA_HERE; // MultipartFile | 
final String name = name_example; // String | 
final String subject = subject_example; // String | 

try {
    final response = api.createTestTestsPost(manual, modelAnswer, name, subject);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->createTestTestsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **manual** | **MultipartFile**|  | 
 **modelAnswer** | **MultipartFile**|  | 
 **name** | **String**|  | 
 **subject** | **String**|  | [optional] 

### Return type

[**TestResponse**](TestResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: multipart/form-data
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **detectAnswerAreasTestsTestIdAnswerLayoutDetectPost**
> ProfileResponse detectAnswerAreasTestsTestIdAnswerLayoutDetectPost(testId)

Detect Answer Areas

Detect this test's answer areas on the stored answer sheet and save them as DRAFT profile regions (Issue #105).  Safe to call again -- like `analyze_profile`, it overwrites whatever DRAFT profile was there and bumps `revision` so a confirm pinned to the previous one is rejected. Refused once the profile is confirmed.  **Every page goes to the provider, once per test.** Grading sends one cropped answer per question per submission; this sends whole pages, and only here (simplified-design-specification.md §26.1.1). Whatever is printed or handwritten on those pages goes with them.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 

try {
    final response = api.detectAnswerAreasTestsTestIdAnswerLayoutDetectPost(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->detectAnswerAreasTestsTestIdAnswerLayoutDetectPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**ProfileResponse**](ProfileResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getAnswerLayoutPdfTestsTestIdAnswerLayoutPdfGet**
> Uint8List getAnswerLayoutPdfTestsTestIdAnswerLayoutPdfGet(testId)

Get Answer Layout Pdf

The stored answer sheet's bytes, for the overlay editor to draw on.  Returned as a PDF rather than page images: the app already renders PDFs with `pdfrx` and places normalized overlays on them (`features/pdf_review`), so serving pictures would mean a second rendering path and a second set of coordinate bugs.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 

try {
    final response = api.getAnswerLayoutPdfTestsTestIdAnswerLayoutPdfGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->getAnswerLayoutPdfTestsTestIdAnswerLayoutPdfGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**Uint8List**](Uint8List.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/pdf, application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getAnswerLayoutTestsTestIdAnswerLayoutGet**
> AnswerLayoutResponse getAnswerLayoutTestsTestIdAnswerLayoutGet(testId)

Get Answer Layout

Whether a reference answer sheet is stored, and whether detection can run on this host.  The screen asks this first so it can say *why* the 自動検出 button is disabled -- an unconfigured provider and a missing answer sheet are different problems with different fixes, and the reviewer can draw the boxes by hand in either case.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 

try {
    final response = api.getAnswerLayoutTestsTestIdAnswerLayoutGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->getAnswerLayoutTestsTestIdAnswerLayoutGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**AnswerLayoutResponse**](AnswerLayoutResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getProfileTestsTestIdProfileGet**
> ProfileResponse getProfileTestsTestIdProfileGet(testId)

Get Profile

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 

try {
    final response = api.getProfileTestsTestIdProfileGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->getProfileTestsTestIdProfileGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**ProfileResponse**](ProfileResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getTestTestsTestIdGet**
> TestResponse getTestTestsTestIdGet(testId)

Get Test

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 

try {
    final response = api.getTestTestsTestIdGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->getTestTestsTestIdGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**TestResponse**](TestResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listTestRegistrationsTestRegistrationsGet**
> BuiltList<TestResponse> listTestRegistrationsTestRegistrationsGet()

List Test Registrations

Every test regardless of status (draft or ready), for the テスト 設定画面's own entry point.  `GET /tests` (api.app, answer intake's test picker) only returns `ready` tests -- a `draft` test has no other way to be found again once its `TestSettingsPage` is closed (Issue #16 review: leaving registration mid-way, or restarting the app, must not make an already-uploaded, persisted draft unreachable).

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();

try {
    final response = api.listTestRegistrationsTestRegistrationsGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->listTestRegistrationsTestRegistrationsGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**BuiltList&lt;TestResponse&gt;**](TestResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateProfileTestsTestIdProfilePut**
> ProfileResponse updateProfileTestsTestIdProfilePut(testId, updateProfileRequest)

Update Profile

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 
final UpdateProfileRequest updateProfileRequest = ; // UpdateProfileRequest | 

try {
    final response = api.updateProfileTestsTestIdProfilePut(testId, updateProfileRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->updateProfileTestsTestIdProfilePut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **updateProfileRequest** | [**UpdateProfileRequest**](UpdateProfileRequest.md)|  | 

### Return type

[**ProfileResponse**](ProfileResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **uploadAnswerLayoutTestsTestIdAnswerLayoutPut**
> AnswerLayoutResponse uploadAnswerLayoutTestsTestIdAnswerLayoutPut(testId, file)

Upload Answer Layout

Store one student's answer sheet as the layout reference for this test (Issue #105).  ``PUT``, not ``POST``: there is exactly one per test and re-uploading replaces it. Kept separate from ``/detect`` so a provider failure -- the common case, since detection is one long multimodal call -- can be retried without asking the reviewer for the file again.  This is not a submission. It gets no `Submission` row and is never graded; it exists because the boxes have to be drawn on *something*, and a test cannot accept real submissions until they are drawn (`adapters.submission_intake.intake_submission` refuses a test that is not ``ready``).  Fully validated -- including per-page render size -- *before* it replaces whatever is already stored, in a scratch directory the same way `intake_submission` does it. A corrupt or absurdly-sized upload must not destroy the sheet the current answer areas were drawn on, and must not be discovered later by an out-of-memory render inside `/detect`.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 
final MultipartFile file = BINARY_DATA_HERE; // MultipartFile | 

try {
    final response = api.uploadAnswerLayoutTestsTestIdAnswerLayoutPut(testId, file);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->uploadAnswerLayoutTestsTestIdAnswerLayoutPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **file** | **MultipartFile**|  | 

### Return type

[**AnswerLayoutResponse**](AnswerLayoutResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: multipart/form-data
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)


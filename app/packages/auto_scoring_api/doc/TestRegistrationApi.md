# auto_scoring_api.api.TestRegistrationApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**addMaterialsTestsTestIdMaterialsPost**](TestRegistrationApi.md#addmaterialsteststestidmaterialspost) | **POST** /tests/{test_id}/materials | Add Materials
[**analyzeProfileTestsTestIdProfileAnalyzePost**](TestRegistrationApi.md#analyzeprofileteststestidprofileanalyzepost) | **POST** /tests/{test_id}/profile/analyze | Analyze Profile
[**completeRegistrationTestsTestIdCompleteRegistrationPost**](TestRegistrationApi.md#completeregistrationteststestidcompleteregistrationpost) | **POST** /tests/{test_id}/complete-registration | Complete Registration
[**confirmProfileTestsTestIdProfileConfirmPost**](TestRegistrationApi.md#confirmprofileteststestidprofileconfirmpost) | **POST** /tests/{test_id}/profile/confirm | Confirm Profile
[**createTestTestsPost**](TestRegistrationApi.md#createtesttestspost) | **POST** /tests | Create Test
[**deleteTestTestsTestIdDelete**](TestRegistrationApi.md#deletetestteststestiddelete) | **DELETE** /tests/{test_id} | Delete Test
[**detectAnswerAreasTestsTestIdAnswerLayoutDetectPost**](TestRegistrationApi.md#detectanswerareasteststestidanswerlayoutdetectpost) | **POST** /tests/{test_id}/answer-layout/detect | Detect Answer Areas
[**getAnswerLayoutPdfTestsTestIdAnswerLayoutPdfGet**](TestRegistrationApi.md#getanswerlayoutpdfteststestidanswerlayoutpdfget) | **GET** /tests/{test_id}/answer-layout/pdf | Get Answer Layout Pdf
[**getAnswerLayoutTestsTestIdAnswerLayoutGet**](TestRegistrationApi.md#getanswerlayoutteststestidanswerlayoutget) | **GET** /tests/{test_id}/answer-layout | Get Answer Layout
[**getProfileTestsTestIdProfileGet**](TestRegistrationApi.md#getprofileteststestidprofileget) | **GET** /tests/{test_id}/profile | Get Profile
[**getTestTestsTestIdGet**](TestRegistrationApi.md#gettestteststestidget) | **GET** /tests/{test_id} | Get Test
[**listMaterialsTestsTestIdMaterialsGet**](TestRegistrationApi.md#listmaterialsteststestidmaterialsget) | **GET** /tests/{test_id}/materials | List Materials
[**listTestRegistrationsTestRegistrationsGet**](TestRegistrationApi.md#listtestregistrationstestregistrationsget) | **GET** /test-registrations | List Test Registrations
[**setScoringTargetsTestsTestIdScoringTargetsPut**](TestRegistrationApi.md#setscoringtargetsteststestidscoringtargetsput) | **PUT** /tests/{test_id}/scoring-targets | Set Scoring Targets
[**updateProfileTestsTestIdProfilePut**](TestRegistrationApi.md#updateprofileteststestidprofileput) | **PUT** /tests/{test_id}/profile | Update Profile
[**uploadAnswerLayoutTestsTestIdAnswerLayoutPut**](TestRegistrationApi.md#uploadanswerlayoutteststestidanswerlayoutput) | **PUT** /tests/{test_id}/answer-layout | Upload Answer Layout


# **addMaterialsTestsTestIdMaterialsPost**
> BuiltList<TestMaterialResponse> addMaterialsTestsTestIdMaterialsPost(testId, materialRoles, materials)

Add Materials

Attach more materials to a test that already exists.  The weekly flow needs this in both directions: answers for an already-registered test arrive as submissions, and a 添削資料 that turns up later must be attachable without re-registering the test.  Re-sending a file already attached under the same role returns the existing material instead of a second copy, so retrying a batch that failed part-way through is safe (Issue #101: 成功した分は残る).

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 
final BuiltList<String> materialRoles = ; // BuiltList<String> | 
final BuiltList<MultipartFile> materials = /path/to/file.txt; // BuiltList<MultipartFile> | 

try {
    final response = api.addMaterialsTestsTestIdMaterialsPost(testId, materialRoles, materials);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->addMaterialsTestsTestIdMaterialsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **materialRoles** | [**BuiltList&lt;String&gt;**](String.md)|  | 
 **materials** | [**BuiltList&lt;MultipartFile&gt;**](MultipartFile.md)|  | 

### Return type

[**BuiltList&lt;TestMaterialResponse&gt;**](TestMaterialResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: multipart/form-data
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

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
> TestResponse createTestTestsPost(criteria, name, materialRoles, materials, subject)

Create Test

Register a test from its 採点基準PDF plus any optional materials.  ``criteria`` is the one required file (Issue #95 decision 1). **There is no model-answer parameter**: that document does not exist in real grading material, and requiring it is what made this screen unusable. A model answer a reviewer happens to have goes in ``materials`` with the ``reference`` role like any other extra file.  Registering does **not** make the test gradable. Points and rubrics still have to come from somewhere, and extracting them from the criteria PDF is separate work (Issue #95 decision A) -- callers must say so rather than implying grading can start.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final MultipartFile criteria = BINARY_DATA_HERE; // MultipartFile | 
final String name = name_example; // String | 
final BuiltList<String> materialRoles = ; // BuiltList<String> | 
final BuiltList<MultipartFile> materials = /path/to/file.txt; // BuiltList<MultipartFile> | 
final String subject = subject_example; // String | 

try {
    final response = api.createTestTestsPost(criteria, name, materialRoles, materials, subject);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->createTestTestsPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **criteria** | **MultipartFile**|  | 
 **name** | **String**|  | 
 **materialRoles** | [**BuiltList&lt;String&gt;**](String.md)|  | [optional] 
 **materials** | [**BuiltList&lt;MultipartFile&gt;**](MultipartFile.md)|  | [optional] 
 **subject** | **String**|  | [optional] 

### Return type

[**TestResponse**](TestResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: multipart/form-data
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **deleteTestTestsTestIdDelete**
> deleteTestTestsTestIdDelete(testId)

Delete Test

Delete a test and everything under it.  Exposed because importing into the wrong test is an ordinary mistake, not an exotic one: the reviewer finds out after the fact, and without this the only remedy would be editing `app-data/` by hand. The bulk delete itself already existed (`adapters.purge.purge_test`: rows cascade, files are removed, and the deletion is written to the audit log per business-rules §2 (11)) -- it simply had no HTTP route.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 

try {
    api.deleteTestTestsTestIdDelete(testId);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->deleteTestTestsTestIdDelete: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

void (empty response body)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
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

The stored answer sheet's raw bytes.  **Used by the Flutter answer-area editor until the Electron cut-over**, and by nothing else. It renders the PDF itself with `pdfrx` and places normalized overlays on the result (`features/pdf_review`).  This endpoint used to justify itself with that rendering path -- \"the app already renders PDFs with pdfrx, so serving pictures would mean a second rendering path and a second set of coordinate bugs\". **Issue #201 removes that premise**: Electron has no `pdfrx`, and PoC 6 (`docs/poc-6-pdf-coordinates.md`) chose the opposite arrangement -- the sidecar rasterizes and the renderer displays the picture, so there is exactly one rendering path and it is the one that also does the coordinate transform. The new UI uses `api.page_image_router` (``GET /tests/{test_id}/answer-layout/pages`` and ``.../pages/{page_index}/image``) and **never receives raw PDF bytes**: app-data stays owned by the sidecar.  **After the cut-over there is no known caller left.** Nothing outside the Flutter app reads it: answer-area detection, criteria extraction and PDF export all open the stored file directly. It is kept rather than deleted here only because the Flutter app still runs.  **Whether to delete this endpoint (and ``GET /submissions/{submission_id}/source-pdf``, kept for the same reason) is decided at cut-over, tracked in Issue #201.** There is no separate cut-over Issue yet; when one is split out, move the item and update this reference. Leaving a reason behind that has stopped being true is the failure this repository has repeated (#111 -> #138).

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

# **listMaterialsTestsTestIdMaterialsGet**
> BuiltList<TestMaterialResponse> listMaterialsTestsTestIdMaterialsGet(testId)

List Materials

Which file became which role for this test.  The answer to \"did my 採点基準 actually land as the 採点基準?\", which is only answerable after import if the name the reviewer chose the file by survives -- so `original_filename` is carried through.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 

try {
    final response = api.listMaterialsTestsTestIdMaterialsGet(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->listMaterialsTestsTestIdMaterialsGet: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 

### Return type

[**BuiltList&lt;TestMaterialResponse&gt;**](TestMaterialResponse.md)

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

# **setScoringTargetsTestsTestIdScoringTargetsPut**
> ScoringTargetsResponse setScoringTargetsTestsTestIdScoringTargetsPut(testId, scoringTargetsRequest)

Set Scoring Targets

Choose which of a test's questions are graded (Issue #449).  The default is every question; this replaces the selection with exactly ``question_ids``. Allowed before *and* after registration completes (the owner changes their mind), but never to an empty set -- a test with nothing to grade has no meaning, so at least one question must stay selected. Excluding a question deletes nothing: its grade and review history are kept, simply not counted or exported, and reappear if it is selected again.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 
final ScoringTargetsRequest scoringTargetsRequest = ; // ScoringTargetsRequest | 

try {
    final response = api.setScoringTargetsTestsTestIdScoringTargetsPut(testId, scoringTargetsRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->setScoringTargetsTestsTestIdScoringTargetsPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **testId** | **String**|  | 
 **scoringTargetsRequest** | [**ScoringTargetsRequest**](ScoringTargetsRequest.md)|  | 

### Return type

[**ScoringTargetsResponse**](ScoringTargetsResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
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


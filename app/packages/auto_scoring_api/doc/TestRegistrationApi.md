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
[**getProfileTestsTestIdProfileGet**](TestRegistrationApi.md#getprofileteststestidprofileget) | **GET** /tests/{test_id}/profile | Get Profile
[**getTestTestsTestIdGet**](TestRegistrationApi.md#gettestteststestidget) | **GET** /tests/{test_id} | Get Test
[**updateProfileTestsTestIdProfilePut**](TestRegistrationApi.md#updateprofileteststestidprofileput) | **PUT** /tests/{test_id}/profile | Update Profile


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
> ProfileResponse confirmProfileTestsTestIdProfileConfirmPost(testId)

Confirm Profile

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getTestRegistrationApi();
final String testId = testId_example; // String | 

try {
    final response = api.confirmProfileTestsTestIdProfileConfirmPost(testId);
    print(response);
} on DioException catch (e) {
    print('Exception when calling TestRegistrationApi->confirmProfileTestsTestIdProfileConfirmPost: $e\n');
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


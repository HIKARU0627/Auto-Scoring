# auto_scoring_api.api.DefaultApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**healthzHealthzGet**](DefaultApi.md#healthzhealthzget) | **GET** /healthz | Healthz
[**scoreScorePost**](DefaultApi.md#scorescorepost) | **POST** /score | Score


# **healthzHealthzGet**
> BuiltMap<String, String> healthzHealthzGet()

Healthz

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDefaultApi();

try {
    final response = api.healthzHealthzGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling DefaultApi->healthzHealthzGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**BuiltMap&lt;String, String&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **scoreScorePost**
> ScoreResponse scoreScorePost(scoreRequest)

Score

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getDefaultApi();
final ScoreRequest scoreRequest = ; // ScoreRequest | 

try {
    final response = api.scoreScorePost(scoreRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling DefaultApi->scoreScorePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **scoreRequest** | [**ScoreRequest**](ScoreRequest.md)|  | 

### Return type

[**ScoreResponse**](ScoreResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)


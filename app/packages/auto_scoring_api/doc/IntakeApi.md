# auto_scoring_api.api.IntakeApi

## Load the API package
```dart
import 'package:auto_scoring_api/api.dart';
```

All URIs are relative to *http://localhost*

Method | HTTP request | Description
------------- | ------------- | -------------
[**attributeAnswerIntakeAttributePost**](IntakeApi.md#attributeanswerintakeattributepost) | **POST** /intake/attribute | Attribute Answer
[**classificationAvailabilityIntakeClassificationAvailabilityGet**](IntakeApi.md#classificationavailabilityintakeclassificationavailabilityget) | **GET** /intake/classification-availability | Classification Availability
[**classifyMaterialIntakeClassifyPost**](IntakeApi.md#classifymaterialintakeclassifypost) | **POST** /intake/classify | Classify Material
[**getIntakeCostIntakeCostGet**](IntakeApi.md#getintakecostintakecostget) | **GET** /intake-cost | Get Intake Cost
[**listTemplatesIntakeTemplatesGet**](IntakeApi.md#listtemplatesintaketemplatesget) | **GET** /intake-templates | List Templates
[**planIntakeIntakePlanPost**](IntakeApi.md#planintakeintakeplanpost) | **POST** /intake/plan | Plan Intake
[**saveIntakeCostIntakeCostPut**](IntakeApi.md#saveintakecostintakecostput) | **PUT** /intake-cost | Save Intake Cost
[**saveTemplatesIntakeTemplatesPut**](IntakeApi.md#savetemplatesintaketemplatesput) | **PUT** /intake-templates | Save Templates


# **attributeAnswerIntakeAttributePost**
> AttributionProposalResponse attributeAnswerIntakeAttributePost(candidateIds, candidateLabels, file)

Attribute Answer

Ask which of the offered tests one answer belongs to.  The candidate set is the caller's: the tests this batch would create plus the already-registered ones the reviewer has narrowed to. **A caller with a single candidate must not call this at all** -- the reviewer has already decided, and asking a provider to choose from a list of one spends money to confirm a foregone conclusion. That is the ordinary case from week two onward, which is why the reviewer's narrowing step is the real cost control here and the classifier is the fallback.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getIntakeApi();
final BuiltList<String> candidateIds = ; // BuiltList<String> | 
final BuiltList<String> candidateLabels = ; // BuiltList<String> | 
final MultipartFile file = BINARY_DATA_HERE; // MultipartFile | 

try {
    final response = api.attributeAnswerIntakeAttributePost(candidateIds, candidateLabels, file);
    print(response);
} on DioException catch (e) {
    print('Exception when calling IntakeApi->attributeAnswerIntakeAttributePost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **candidateIds** | [**BuiltList&lt;String&gt;**](String.md)|  | 
 **candidateLabels** | [**BuiltList&lt;String&gt;**](String.md)|  | 
 **file** | **MultipartFile**|  | 

### Return type

[**AttributionProposalResponse**](AttributionProposalResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: multipart/form-data
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **classificationAvailabilityIntakeClassificationAvailabilityGet**
> ClassificationAvailabilityResponse classificationAvailabilityIntakeClassificationAvailabilityGet()

Classification Availability

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getIntakeApi();

try {
    final response = api.classificationAvailabilityIntakeClassificationAvailabilityGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling IntakeApi->classificationAvailabilityIntakeClassificationAvailabilityGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**ClassificationAvailabilityResponse**](ClassificationAvailabilityResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **classifyMaterialIntakeClassifyPost**
> RoleProposalResponse classifyMaterialIntakeClassifyPost(file)

Classify Material

Propose what one file is, from its first page.  Callers send only files a template's rules did not match: a matched file must never reach this endpoint (acceptance criterion 8). Nothing here enforces that -- there is no way for this endpoint to know which template the caller used -- so the guarantee lives where the decision is made, in `domain.intake_plan.build_plan` and its tests.

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getIntakeApi();
final MultipartFile file = BINARY_DATA_HERE; // MultipartFile | 

try {
    final response = api.classifyMaterialIntakeClassifyPost(file);
    print(response);
} on DioException catch (e) {
    print('Exception when calling IntakeApi->classifyMaterialIntakeClassifyPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **file** | **MultipartFile**|  | 

### Return type

[**RoleProposalResponse**](RoleProposalResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: multipart/form-data
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getIntakeCostIntakeCostGet**
> IntakeCostModel getIntakeCostIntakeCostGet()

Get Intake Cost

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getIntakeApi();

try {
    final response = api.getIntakeCostIntakeCostGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling IntakeApi->getIntakeCostIntakeCostGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**IntakeCostModel**](IntakeCostModel.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listTemplatesIntakeTemplatesGet**
> BuiltList<IntakeTemplateModel> listTemplatesIntakeTemplatesGet()

List Templates

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getIntakeApi();

try {
    final response = api.listTemplatesIntakeTemplatesGet();
    print(response);
} on DioException catch (e) {
    print('Exception when calling IntakeApi->listTemplatesIntakeTemplatesGet: $e\n');
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**BuiltList&lt;IntakeTemplateModel&gt;**](IntakeTemplateModel.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **planIntakeIntakePlanPost**
> IntakePlanResponse planIntakeIntakePlanPost(planRequest)

Plan Intake

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getIntakeApi();
final PlanRequest planRequest = ; // PlanRequest | 

try {
    final response = api.planIntakeIntakePlanPost(planRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling IntakeApi->planIntakeIntakePlanPost: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **planRequest** | [**PlanRequest**](PlanRequest.md)|  | 

### Return type

[**IntakePlanResponse**](IntakePlanResponse.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **saveIntakeCostIntakeCostPut**
> IntakeCostModel saveIntakeCostIntakeCostPut(intakeCostModel)

Save Intake Cost

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getIntakeApi();
final IntakeCostModel intakeCostModel = ; // IntakeCostModel | 

try {
    final response = api.saveIntakeCostIntakeCostPut(intakeCostModel);
    print(response);
} on DioException catch (e) {
    print('Exception when calling IntakeApi->saveIntakeCostIntakeCostPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **intakeCostModel** | [**IntakeCostModel**](IntakeCostModel.md)|  | 

### Return type

[**IntakeCostModel**](IntakeCostModel.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **saveTemplatesIntakeTemplatesPut**
> BuiltList<IntakeTemplateModel> saveTemplatesIntakeTemplatesPut(saveTemplatesRequest)

Save Templates

### Example
```dart
import 'package:auto_scoring_api/api.dart';

final api = AutoScoringApi().getIntakeApi();
final SaveTemplatesRequest saveTemplatesRequest = ; // SaveTemplatesRequest | 

try {
    final response = api.saveTemplatesIntakeTemplatesPut(saveTemplatesRequest);
    print(response);
} on DioException catch (e) {
    print('Exception when calling IntakeApi->saveTemplatesIntakeTemplatesPut: $e\n');
}
```

### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **saveTemplatesRequest** | [**SaveTemplatesRequest**](SaveTemplatesRequest.md)|  | 

### Return type

[**BuiltList&lt;IntakeTemplateModel&gt;**](IntakeTemplateModel.md)

### Authorization

[HTTPBearer](../README.md#HTTPBearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)


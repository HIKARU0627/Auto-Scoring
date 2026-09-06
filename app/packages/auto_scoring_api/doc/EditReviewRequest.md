# auto_scoring_api.model.EditReviewRequest

## Load the model package
```dart
import 'package:auto_scoring_api/api.dart';
```

## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**annotations** | [**BuiltList&lt;AnnotationEditRequest&gt;**](AnnotationEditRequest.md) |  | [optional] 
**comment** | **String** |  | [optional] 
**confidence** | **num** |  | [optional] [default to 1.0]
**criteria** | [**BuiltList&lt;CriterionOutcomeRequest&gt;**](CriterionOutcomeRequest.md) |  | [optional] 
**expectedVersion** | **int** |  | 
**note** | **String** |  | [optional] 
**rationale** | **String** |  | [optional] 
**recognizedText** | **String** |  | [optional] 
**scoreAwarded** | **int** |  | 
**scoreMaximum** | **int** |  | 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)



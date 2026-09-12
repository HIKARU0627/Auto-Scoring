# auto_scoring_api.model.QuestionResponse

## Load the model package
```dart
import 'package:auto_scoring_api/api.dart';
```

## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**answerArea** | [**NormalizedRectResponse**](NormalizedRectResponse.md) |  | [optional] 
**commentArea** | [**NormalizedRectResponse**](NormalizedRectResponse.md) |  | [optional] 
**id** | **String** |  | 
**isScoringTarget** | **bool** |  | [optional] [default to true]
**modelAnswer** | **String** |  | [optional] 
**number** | **String** |  | 
**page** | **int** |  | 
**points** | **int** |  | 
**rubric** | [**BuiltList&lt;RubricCriterionResponse&gt;**](RubricCriterionResponse.md) |  | 
**scoreArea** | [**NormalizedRectResponse**](NormalizedRectResponse.md) |  | [optional] 
**scorePlacement** | [**QuestionScorePlacementResponse**](QuestionScorePlacementResponse.md) |  | [optional] 
**scoringMethod** | **String** |  | 
**testId** | **String** |  | 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)



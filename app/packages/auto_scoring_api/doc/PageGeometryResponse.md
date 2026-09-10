# auto_scoring_api.model.PageGeometryResponse

## Load the model package
```dart
import 'package:auto_scoring_api/api.dart';
```

## Properties
Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**displayedHeight** | **num** | Height in PDF points of the page as pdfium displays it (CropBox∩MediaBox, after /Rotate). For sizing a placeholder, not for dividing a click position. | 
**displayedWidth** | **num** | Width in PDF points of the page as pdfium displays it (CropBox∩MediaBox, after /Rotate). For sizing a placeholder, not for dividing a click position. | 
**pageIndex** | **int** | 0-based index of this page. | 
**rotation** | **int** | The page's /Rotate, reduced to 0, 90, 180 or 270. | 

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)



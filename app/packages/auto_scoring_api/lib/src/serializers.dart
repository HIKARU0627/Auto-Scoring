//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_import

import 'package:one_of_serializer/any_of_serializer.dart';
import 'package:one_of_serializer/one_of_serializer.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/json_object.dart';
import 'package:built_value/serializer.dart';
import 'package:built_value/standard_json_plugin.dart';
import 'package:built_value/iso_8601_date_time_serializer.dart';
import 'package:auto_scoring_api/src/date_serializer.dart';
import 'package:auto_scoring_api/src/model/date.dart';

import 'package:auto_scoring_api/src/model/http_validation_error.dart';
import 'package:auto_scoring_api/src/model/location_inner.dart';
import 'package:auto_scoring_api/src/model/score_request.dart';
import 'package:auto_scoring_api/src/model/score_response.dart';
import 'package:auto_scoring_api/src/model/submission_response.dart';
import 'package:auto_scoring_api/src/model/test_summary.dart';
import 'package:auto_scoring_api/src/model/validation_error.dart';

part 'serializers.g.dart';

@SerializersFor([
  HTTPValidationError,
  LocationInner,
  ScoreRequest,
  ScoreResponse,
  SubmissionResponse,
  TestSummary,
  ValidationError,
])
Serializers serializers = (_$serializers.toBuilder()
      ..addBuilderFactory(
        const FullType(BuiltMap, [FullType(String), FullType(String)]),
        () => MapBuilder<String, String>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(LocationInner)]),
        () => ListBuilder<LocationInner>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(SubmissionResponse)]),
        () => ListBuilder<SubmissionResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(ValidationError)]),
        () => ListBuilder<ValidationError>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TestSummary)]),
        () => ListBuilder<TestSummary>(),
      )
      ..add(const OneOfSerializer())
      ..add(const AnyOfSerializer())
      ..add(const DateSerializer())
      ..add(Iso8601DateTimeSerializer()))
    .build();

Serializers standardSerializers =
    (serializers.toBuilder()..addPlugin(StandardJsonPlugin())).build();

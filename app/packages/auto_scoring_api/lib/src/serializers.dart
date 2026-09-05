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

import 'package:auto_scoring_api/src/model/analyze_request.dart';
import 'package:auto_scoring_api/src/model/confirm_request.dart';
import 'package:auto_scoring_api/src/model/dependency_edge_model.dart';
import 'package:auto_scoring_api/src/model/dependency_graph_response.dart';
import 'package:auto_scoring_api/src/model/dependency_provision.dart';
import 'package:auto_scoring_api/src/model/http_validation_error.dart';
import 'package:auto_scoring_api/src/model/job_response.dart';
import 'package:auto_scoring_api/src/model/location_inner.dart';
import 'package:auto_scoring_api/src/model/question_text_override.dart';
import 'package:auto_scoring_api/src/model/score_request.dart';
import 'package:auto_scoring_api/src/model/score_response.dart';
import 'package:auto_scoring_api/src/model/submission_response.dart';
import 'package:auto_scoring_api/src/model/test_summary.dart';
import 'package:auto_scoring_api/src/model/unresolved_question_model.dart';
import 'package:auto_scoring_api/src/model/validation_error.dart';

part 'serializers.g.dart';

@SerializersFor([
  AnalyzeRequest,
  ConfirmRequest,
  DependencyEdgeModel,
  DependencyGraphResponse,
  DependencyProvision,
  HTTPValidationError,
  JobResponse,
  LocationInner,
  QuestionTextOverride,
  ScoreRequest,
  ScoreResponse,
  SubmissionResponse,
  TestSummary,
  UnresolvedQuestionModel,
  ValidationError,
])
Serializers serializers = (_$serializers.toBuilder()
      ..addBuilderFactory(
        const FullType(BuiltMap, [FullType(String), FullType(String)]),
        () => MapBuilder<String, String>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(DependencyGraphResponse)]),
        () => ListBuilder<DependencyGraphResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(JobResponse)]),
        () => ListBuilder<JobResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(SubmissionResponse)]),
        () => ListBuilder<SubmissionResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TestSummary)]),
        () => ListBuilder<TestSummary>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(DependencyEdgeModel)]),
        () => ListBuilder<DependencyEdgeModel>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [
          FullType(BuiltList, [FullType(String)])
        ]),
        () => ListBuilder<BuiltList<String>>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(UnresolvedQuestionModel)]),
        () => ListBuilder<UnresolvedQuestionModel>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(LocationInner)]),
        () => ListBuilder<LocationInner>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(QuestionTextOverride)]),
        () => ListBuilder<QuestionTextOverride>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(ValidationError)]),
        () => ListBuilder<ValidationError>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(DependencyProvision)]),
        () => ListBuilder<DependencyProvision>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(String)]),
        () => ListBuilder<String>(),
      )
      ..add(const OneOfSerializer())
      ..add(const AnyOfSerializer())
      ..add(const DateSerializer())
      ..add(Iso8601DateTimeSerializer()))
    .build();

Serializers standardSerializers =
    (serializers.toBuilder()..addPlugin(StandardJsonPlugin())).build();

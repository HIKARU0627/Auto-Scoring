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
import 'package:auto_scoring_api/src/model/annotation_edit_request.dart';
import 'package:auto_scoring_api/src/model/annotation_response.dart';
import 'package:auto_scoring_api/src/model/approve_review_request.dart';
import 'package:auto_scoring_api/src/model/bounding_box_response.dart';
import 'package:auto_scoring_api/src/model/complete_registration_response.dart';
import 'package:auto_scoring_api/src/model/confirm_profile_request.dart';
import 'package:auto_scoring_api/src/model/confirm_request.dart';
import 'package:auto_scoring_api/src/model/criterion_outcome_request.dart';
import 'package:auto_scoring_api/src/model/criterion_result_response.dart';
import 'package:auto_scoring_api/src/model/dependency_edge_model.dart';
import 'package:auto_scoring_api/src/model/dependency_graph_response.dart';
import 'package:auto_scoring_api/src/model/dependency_provision.dart';
import 'package:auto_scoring_api/src/model/edit_review_request.dart';
import 'package:auto_scoring_api/src/model/grade_result_response.dart';
import 'package:auto_scoring_api/src/model/http_validation_error.dart';
import 'package:auto_scoring_api/src/model/job_response.dart';
import 'package:auto_scoring_api/src/model/location_inner.dart';
import 'package:auto_scoring_api/src/model/manual_recognition_request.dart';
import 'package:auto_scoring_api/src/model/normalized_b_box_model.dart';
import 'package:auto_scoring_api/src/model/normalized_rect_response.dart';
import 'package:auto_scoring_api/src/model/page_format_model.dart';
import 'package:auto_scoring_api/src/model/profile_response.dart';
import 'package:auto_scoring_api/src/model/question_response.dart';
import 'package:auto_scoring_api/src/model/question_text_override.dart';
import 'package:auto_scoring_api/src/model/reasoned_review_request.dart';
import 'package:auto_scoring_api/src/model/recognition_response.dart';
import 'package:auto_scoring_api/src/model/recognition_response_slim.dart';
import 'package:auto_scoring_api/src/model/region_kind.dart';
import 'package:auto_scoring_api/src/model/region_model.dart';
import 'package:auto_scoring_api/src/model/review_action_response.dart';
import 'package:auto_scoring_api/src/model/review_response.dart';
import 'package:auto_scoring_api/src/model/rubric_criterion_response.dart';
import 'package:auto_scoring_api/src/model/score_request.dart';
import 'package:auto_scoring_api/src/model/score_response.dart';
import 'package:auto_scoring_api/src/model/score_value_response.dart';
import 'package:auto_scoring_api/src/model/submission_response.dart';
import 'package:auto_scoring_api/src/model/test_response.dart';
import 'package:auto_scoring_api/src/model/test_summary.dart';
import 'package:auto_scoring_api/src/model/undo_review_request.dart';
import 'package:auto_scoring_api/src/model/unresolved_question_model.dart';
import 'package:auto_scoring_api/src/model/update_profile_request.dart';
import 'package:auto_scoring_api/src/model/validation_error.dart';

part 'serializers.g.dart';

@SerializersFor([
  AnalyzeRequest,
  AnnotationEditRequest,
  AnnotationResponse,
  ApproveReviewRequest,
  BoundingBoxResponse,
  CompleteRegistrationResponse,
  ConfirmProfileRequest,
  ConfirmRequest,
  CriterionOutcomeRequest,
  CriterionResultResponse,
  DependencyEdgeModel,
  DependencyGraphResponse,
  DependencyProvision,
  EditReviewRequest,
  GradeResultResponse,
  HTTPValidationError,
  JobResponse,
  LocationInner,
  ManualRecognitionRequest,
  NormalizedBBoxModel,
  NormalizedRectResponse,
  PageFormatModel,
  ProfileResponse,
  QuestionResponse,
  QuestionTextOverride,
  ReasonedReviewRequest,
  RecognitionResponse,
  RecognitionResponseSlim,
  RegionKind,
  RegionModel,
  ReviewActionResponse,
  ReviewResponse,
  RubricCriterionResponse,
  ScoreRequest,
  ScoreResponse,
  ScoreValueResponse,
  SubmissionResponse,
  TestResponse,
  TestSummary,
  UndoReviewRequest,
  UnresolvedQuestionModel,
  UpdateProfileRequest,
  ValidationError,
])
Serializers serializers = (_$serializers.toBuilder()
      ..addBuilderFactory(
        const FullType(BuiltMap, [FullType(String), FullType(String)]),
        () => MapBuilder<String, String>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(CriterionOutcomeRequest)]),
        () => ListBuilder<CriterionOutcomeRequest>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(BoundingBoxResponse)]),
        () => ListBuilder<BoundingBoxResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(DependencyGraphResponse)]),
        () => ListBuilder<DependencyGraphResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(SubmissionResponse)]),
        () => ListBuilder<SubmissionResponse>(),
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
        const FullType(BuiltList, [FullType(GradeResultResponse)]),
        () => ListBuilder<GradeResultResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(LocationInner)]),
        () => ListBuilder<LocationInner>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(DependencyProvision)]),
        () => ListBuilder<DependencyProvision>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(RegionModel)]),
        () => ListBuilder<RegionModel>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(AnnotationResponse)]),
        () => ListBuilder<AnnotationResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(PageFormatModel)]),
        () => ListBuilder<PageFormatModel>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(JobResponse)]),
        () => ListBuilder<JobResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(QuestionResponse)]),
        () => ListBuilder<QuestionResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TestSummary)]),
        () => ListBuilder<TestSummary>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(RecognitionResponse)]),
        () => ListBuilder<RecognitionResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(CriterionResultResponse)]),
        () => ListBuilder<CriterionResultResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(UnresolvedQuestionModel)]),
        () => ListBuilder<UnresolvedQuestionModel>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(ReviewResponse)]),
        () => ListBuilder<ReviewResponse>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(RubricCriterionResponse)]),
        () => ListBuilder<RubricCriterionResponse>(),
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
        const FullType(BuiltList, [FullType(String)]),
        () => ListBuilder<String>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(AnnotationEditRequest)]),
        () => ListBuilder<AnnotationEditRequest>(),
      )
      ..addBuilderFactory(
        const FullType(BuiltList, [FullType(TestResponse)]),
        () => ListBuilder<TestResponse>(),
      )
      ..add(const OneOfSerializer())
      ..add(const AnyOfSerializer())
      ..add(const DateSerializer())
      ..add(Iso8601DateTimeSerializer()))
    .build();

Serializers standardSerializers =
    (serializers.toBuilder()..addPlugin(StandardJsonPlugin())).build();

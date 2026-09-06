//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/annotation_response.dart';
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/grade_result_response.dart';
import 'package:auto_scoring_api/src/model/review_response.dart';
import 'package:auto_scoring_api/src/model/recognition_response_slim.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'review_action_response.g.dart';

/// The new `Review` row plus whatever it produced, and the submission's state right after re-syncing it (Issue #22 acceptance: \"未確認設問が残る Submissionは出力可能状態にならない\") -- so the review screen can update its `SubmissionState` chip without a second round trip.
///
/// Properties:
/// * [annotations]
/// * [grade]
/// * [jobId]
/// * [recognition]
/// * [review]
/// * [submissionState]
@BuiltValue()
abstract class ReviewActionResponse
    implements Built<ReviewActionResponse, ReviewActionResponseBuilder> {
  @BuiltValueField(wireName: r'annotations')
  BuiltList<AnnotationResponse>? get annotations;

  @BuiltValueField(wireName: r'grade')
  GradeResultResponse? get grade;

  @BuiltValueField(wireName: r'job_id')
  String? get jobId;

  @BuiltValueField(wireName: r'recognition')
  RecognitionResponseSlim? get recognition;

  @BuiltValueField(wireName: r'review')
  ReviewResponse get review;

  @BuiltValueField(wireName: r'submission_state')
  String get submissionState;

  ReviewActionResponse._();

  factory ReviewActionResponse([void updates(ReviewActionResponseBuilder b)]) =
      _$ReviewActionResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ReviewActionResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ReviewActionResponse> get serializer =>
      _$ReviewActionResponseSerializer();
}

class _$ReviewActionResponseSerializer
    implements PrimitiveSerializer<ReviewActionResponse> {
  @override
  final Iterable<Type> types = const [
    ReviewActionResponse,
    _$ReviewActionResponse
  ];

  @override
  final String wireName = r'ReviewActionResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ReviewActionResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.annotations != null) {
      yield r'annotations';
      yield serializers.serialize(
        object.annotations,
        specifiedType:
            const FullType(BuiltList, [FullType(AnnotationResponse)]),
      );
    }
    if (object.grade != null) {
      yield r'grade';
      yield serializers.serialize(
        object.grade,
        specifiedType: const FullType.nullable(GradeResultResponse),
      );
    }
    if (object.jobId != null) {
      yield r'job_id';
      yield serializers.serialize(
        object.jobId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.recognition != null) {
      yield r'recognition';
      yield serializers.serialize(
        object.recognition,
        specifiedType: const FullType.nullable(RecognitionResponseSlim),
      );
    }
    yield r'review';
    yield serializers.serialize(
      object.review,
      specifiedType: const FullType(ReviewResponse),
    );
    yield r'submission_state';
    yield serializers.serialize(
      object.submissionState,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ReviewActionResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object,
            specifiedType: specifiedType)
        .toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required ReviewActionResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'annotations':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(
                BuiltList, [FullType(AnnotationResponse)]),
          ) as BuiltList<AnnotationResponse>?;
          if (valueDes == null) continue;
          result.annotations.replace(valueDes);
          break;
        case r'grade':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(GradeResultResponse),
          ) as GradeResultResponse?;
          if (valueDes == null) continue;
          result.grade.replace(valueDes);
          break;
        case r'job_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.jobId = valueDes;
          break;
        case r'recognition':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(RecognitionResponseSlim),
          ) as RecognitionResponseSlim?;
          if (valueDes == null) continue;
          result.recognition.replace(valueDes);
          break;
        case r'review':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(ReviewResponse),
          ) as ReviewResponse;
          result.review.replace(valueDes);
          break;
        case r'submission_state':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.submissionState = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ReviewActionResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ReviewActionResponseBuilder();
    final serializedList = (serialized as Iterable<Object?>).toList();
    final unhandled = <Object?>[];
    _deserializeProperties(
      serializers,
      serialized,
      specifiedType: specifiedType,
      serializedList: serializedList,
      unhandled: unhandled,
      result: result,
    );
    return result.build();
  }
}

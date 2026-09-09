//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'submission_review_progress_response.g.dart';

/// How far one answer has got, counted per question (Issue #113).  **Counts only.** 答案キュー needs three numbers per row and nothing else; the row's own状態 already comes from `SubmissionResponse.state`, and anything richer belongs to the screen that opens the answer.  Why it exists at all: `GET /submissions/{id}/questions/{qid}/reviews` is per-question, so a 40-answer test would cost 200 requests to draw one list -- the same shape ホーム画面 already refuses for jobs (`docs/home-dashboard.md` §4). One request for the whole test instead.
///
/// Properties:
/// * [confirmedQuestions]
/// * [failedQuestions]
/// * [submissionId]
/// * [totalQuestions]
@BuiltValue()
abstract class SubmissionReviewProgressResponse
    implements
        Built<SubmissionReviewProgressResponse,
            SubmissionReviewProgressResponseBuilder> {
  @BuiltValueField(wireName: r'confirmed_questions')
  int get confirmedQuestions;

  @BuiltValueField(wireName: r'failed_questions')
  int get failedQuestions;

  @BuiltValueField(wireName: r'submission_id')
  String get submissionId;

  @BuiltValueField(wireName: r'total_questions')
  int get totalQuestions;

  SubmissionReviewProgressResponse._();

  factory SubmissionReviewProgressResponse(
          [void updates(SubmissionReviewProgressResponseBuilder b)]) =
      _$SubmissionReviewProgressResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(SubmissionReviewProgressResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<SubmissionReviewProgressResponse> get serializer =>
      _$SubmissionReviewProgressResponseSerializer();
}

class _$SubmissionReviewProgressResponseSerializer
    implements PrimitiveSerializer<SubmissionReviewProgressResponse> {
  @override
  final Iterable<Type> types = const [
    SubmissionReviewProgressResponse,
    _$SubmissionReviewProgressResponse
  ];

  @override
  final String wireName = r'SubmissionReviewProgressResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    SubmissionReviewProgressResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'confirmed_questions';
    yield serializers.serialize(
      object.confirmedQuestions,
      specifiedType: const FullType(int),
    );
    yield r'failed_questions';
    yield serializers.serialize(
      object.failedQuestions,
      specifiedType: const FullType(int),
    );
    yield r'submission_id';
    yield serializers.serialize(
      object.submissionId,
      specifiedType: const FullType(String),
    );
    yield r'total_questions';
    yield serializers.serialize(
      object.totalQuestions,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    SubmissionReviewProgressResponse object, {
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
    required SubmissionReviewProgressResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'confirmed_questions':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.confirmedQuestions = valueDes;
          break;
        case r'failed_questions':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.failedQuestions = valueDes;
          break;
        case r'submission_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.submissionId = valueDes;
          break;
        case r'total_questions':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.totalQuestions = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  SubmissionReviewProgressResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = SubmissionReviewProgressResponseBuilder();
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

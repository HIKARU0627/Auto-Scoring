//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'review_response.g.dart';

/// One row of the append-only operation history (Issue #22 §19).  ``version`` is the optimistic-concurrency token a client must echo back (as ``expected_version``) on its *next* mutating call for this submission-question -- see `domain.review_workflow.next_review_version` and `docs/review-edit-history.md` \"同時実行制御\". A client that has never loaded any review for a question passes ``expected_version=0``.
///
/// Properties:
/// * [action]
/// * [aiGradeResultId]
/// * [createdAt]
/// * [humanGradeResultId]
/// * [id]
/// * [note]
/// * [questionId]
/// * [regradeJobId]
/// * [submissionId]
/// * [undoneReviewId]
/// * [version]
@BuiltValue()
abstract class ReviewResponse
    implements Built<ReviewResponse, ReviewResponseBuilder> {
  @BuiltValueField(wireName: r'action')
  String get action;

  @BuiltValueField(wireName: r'ai_grade_result_id')
  String? get aiGradeResultId;

  @BuiltValueField(wireName: r'created_at')
  DateTime get createdAt;

  @BuiltValueField(wireName: r'human_grade_result_id')
  String? get humanGradeResultId;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'note')
  String? get note;

  @BuiltValueField(wireName: r'question_id')
  String get questionId;

  @BuiltValueField(wireName: r'regrade_job_id')
  String? get regradeJobId;

  @BuiltValueField(wireName: r'submission_id')
  String get submissionId;

  @BuiltValueField(wireName: r'undone_review_id')
  String? get undoneReviewId;

  @BuiltValueField(wireName: r'version')
  int get version;

  ReviewResponse._();

  factory ReviewResponse([void updates(ReviewResponseBuilder b)]) =
      _$ReviewResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ReviewResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ReviewResponse> get serializer =>
      _$ReviewResponseSerializer();
}

class _$ReviewResponseSerializer
    implements PrimitiveSerializer<ReviewResponse> {
  @override
  final Iterable<Type> types = const [ReviewResponse, _$ReviewResponse];

  @override
  final String wireName = r'ReviewResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ReviewResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'action';
    yield serializers.serialize(
      object.action,
      specifiedType: const FullType(String),
    );
    if (object.aiGradeResultId != null) {
      yield r'ai_grade_result_id';
      yield serializers.serialize(
        object.aiGradeResultId,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'created_at';
    yield serializers.serialize(
      object.createdAt,
      specifiedType: const FullType(DateTime),
    );
    if (object.humanGradeResultId != null) {
      yield r'human_grade_result_id';
      yield serializers.serialize(
        object.humanGradeResultId,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    if (object.note != null) {
      yield r'note';
      yield serializers.serialize(
        object.note,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'question_id';
    yield serializers.serialize(
      object.questionId,
      specifiedType: const FullType(String),
    );
    if (object.regradeJobId != null) {
      yield r'regrade_job_id';
      yield serializers.serialize(
        object.regradeJobId,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'submission_id';
    yield serializers.serialize(
      object.submissionId,
      specifiedType: const FullType(String),
    );
    if (object.undoneReviewId != null) {
      yield r'undone_review_id';
      yield serializers.serialize(
        object.undoneReviewId,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'version';
    yield serializers.serialize(
      object.version,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ReviewResponse object, {
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
    required ReviewResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'action':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.action = valueDes;
          break;
        case r'ai_grade_result_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.aiGradeResultId = valueDes;
          break;
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(DateTime),
          ) as DateTime;
          result.createdAt = valueDes;
          break;
        case r'human_grade_result_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.humanGradeResultId = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'note':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.note = valueDes;
          break;
        case r'question_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.questionId = valueDes;
          break;
        case r'regrade_job_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.regradeJobId = valueDes;
          break;
        case r'submission_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.submissionId = valueDes;
          break;
        case r'undone_review_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.undoneReviewId = valueDes;
          break;
        case r'version':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.version = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ReviewResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ReviewResponseBuilder();
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

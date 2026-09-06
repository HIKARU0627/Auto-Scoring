//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/annotation_edit_request.dart';
import 'package:auto_scoring_api/src/model/criterion_outcome_request.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'edit_review_request.g.dart';

/// EditReviewRequest
///
/// Properties:
/// * [annotations]
/// * [comment]
/// * [confidence]
/// * [criteria]
/// * [expectedVersion]
/// * [note]
/// * [rationale]
/// * [recognizedText]
/// * [scoreAwarded]
/// * [scoreMaximum]
@BuiltValue()
abstract class EditReviewRequest
    implements Built<EditReviewRequest, EditReviewRequestBuilder> {
  @BuiltValueField(wireName: r'annotations')
  BuiltList<AnnotationEditRequest>? get annotations;

  @BuiltValueField(wireName: r'comment')
  String? get comment;

  @BuiltValueField(wireName: r'confidence')
  num? get confidence;

  @BuiltValueField(wireName: r'criteria')
  BuiltList<CriterionOutcomeRequest>? get criteria;

  @BuiltValueField(wireName: r'expected_version')
  int get expectedVersion;

  @BuiltValueField(wireName: r'note')
  String? get note;

  @BuiltValueField(wireName: r'rationale')
  String? get rationale;

  @BuiltValueField(wireName: r'recognized_text')
  String? get recognizedText;

  @BuiltValueField(wireName: r'score_awarded')
  int get scoreAwarded;

  @BuiltValueField(wireName: r'score_maximum')
  int get scoreMaximum;

  EditReviewRequest._();

  factory EditReviewRequest([void updates(EditReviewRequestBuilder b)]) =
      _$EditReviewRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(EditReviewRequestBuilder b) => b..confidence = 1.0;

  @BuiltValueSerializer(custom: true)
  static Serializer<EditReviewRequest> get serializer =>
      _$EditReviewRequestSerializer();
}

class _$EditReviewRequestSerializer
    implements PrimitiveSerializer<EditReviewRequest> {
  @override
  final Iterable<Type> types = const [EditReviewRequest, _$EditReviewRequest];

  @override
  final String wireName = r'EditReviewRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    EditReviewRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.annotations != null) {
      yield r'annotations';
      yield serializers.serialize(
        object.annotations,
        specifiedType: const FullType.nullable(
            BuiltList, [FullType(AnnotationEditRequest)]),
      );
    }
    if (object.comment != null) {
      yield r'comment';
      yield serializers.serialize(
        object.comment,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.confidence != null) {
      yield r'confidence';
      yield serializers.serialize(
        object.confidence,
        specifiedType: const FullType(num),
      );
    }
    if (object.criteria != null) {
      yield r'criteria';
      yield serializers.serialize(
        object.criteria,
        specifiedType:
            const FullType(BuiltList, [FullType(CriterionOutcomeRequest)]),
      );
    }
    yield r'expected_version';
    yield serializers.serialize(
      object.expectedVersion,
      specifiedType: const FullType(int),
    );
    if (object.note != null) {
      yield r'note';
      yield serializers.serialize(
        object.note,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.rationale != null) {
      yield r'rationale';
      yield serializers.serialize(
        object.rationale,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.recognizedText != null) {
      yield r'recognized_text';
      yield serializers.serialize(
        object.recognizedText,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'score_awarded';
    yield serializers.serialize(
      object.scoreAwarded,
      specifiedType: const FullType(int),
    );
    yield r'score_maximum';
    yield serializers.serialize(
      object.scoreMaximum,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    EditReviewRequest object, {
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
    required EditReviewRequestBuilder result,
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
                BuiltList, [FullType(AnnotationEditRequest)]),
          ) as BuiltList<AnnotationEditRequest>?;
          if (valueDes == null) continue;
          result.annotations.replace(valueDes);
          break;
        case r'comment':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.comment = valueDes;
          break;
        case r'confidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.confidence = valueDes;
          break;
        case r'criteria':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(
                BuiltList, [FullType(CriterionOutcomeRequest)]),
          ) as BuiltList<CriterionOutcomeRequest>?;
          if (valueDes == null) continue;
          result.criteria.replace(valueDes);
          break;
        case r'expected_version':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.expectedVersion = valueDes;
          break;
        case r'note':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.note = valueDes;
          break;
        case r'rationale':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.rationale = valueDes;
          break;
        case r'recognized_text':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.recognizedText = valueDes;
          break;
        case r'score_awarded':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.scoreAwarded = valueDes;
          break;
        case r'score_maximum':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.scoreMaximum = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  EditReviewRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = EditReviewRequestBuilder();
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

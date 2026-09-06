//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/normalized_rect_response.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'annotation_response.g.dart';

/// AnnotationResponse
///
/// Properties:
/// * [anchorText]
/// * [comment]
/// * [createdAt]
/// * [id]
/// * [kind]
/// * [questionId]
/// * [rect]
/// * [source_]
/// * [submissionId]
@BuiltValue()
abstract class AnnotationResponse
    implements Built<AnnotationResponse, AnnotationResponseBuilder> {
  @BuiltValueField(wireName: r'anchor_text')
  String? get anchorText;

  @BuiltValueField(wireName: r'comment')
  String? get comment;

  @BuiltValueField(wireName: r'created_at')
  DateTime get createdAt;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'kind')
  String get kind;

  @BuiltValueField(wireName: r'question_id')
  String get questionId;

  @BuiltValueField(wireName: r'rect')
  NormalizedRectResponse? get rect;

  @BuiltValueField(wireName: r'source')
  String get source_;

  @BuiltValueField(wireName: r'submission_id')
  String get submissionId;

  AnnotationResponse._();

  factory AnnotationResponse([void updates(AnnotationResponseBuilder b)]) =
      _$AnnotationResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(AnnotationResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<AnnotationResponse> get serializer =>
      _$AnnotationResponseSerializer();
}

class _$AnnotationResponseSerializer
    implements PrimitiveSerializer<AnnotationResponse> {
  @override
  final Iterable<Type> types = const [AnnotationResponse, _$AnnotationResponse];

  @override
  final String wireName = r'AnnotationResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    AnnotationResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.anchorText != null) {
      yield r'anchor_text';
      yield serializers.serialize(
        object.anchorText,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.comment != null) {
      yield r'comment';
      yield serializers.serialize(
        object.comment,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'created_at';
    yield serializers.serialize(
      object.createdAt,
      specifiedType: const FullType(DateTime),
    );
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    yield r'kind';
    yield serializers.serialize(
      object.kind,
      specifiedType: const FullType(String),
    );
    yield r'question_id';
    yield serializers.serialize(
      object.questionId,
      specifiedType: const FullType(String),
    );
    if (object.rect != null) {
      yield r'rect';
      yield serializers.serialize(
        object.rect,
        specifiedType: const FullType.nullable(NormalizedRectResponse),
      );
    }
    yield r'source';
    yield serializers.serialize(
      object.source_,
      specifiedType: const FullType(String),
    );
    yield r'submission_id';
    yield serializers.serialize(
      object.submissionId,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    AnnotationResponse object, {
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
    required AnnotationResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'anchor_text':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.anchorText = valueDes;
          break;
        case r'comment':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.comment = valueDes;
          break;
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(DateTime),
          ) as DateTime;
          result.createdAt = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.kind = valueDes;
          break;
        case r'question_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.questionId = valueDes;
          break;
        case r'rect':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(NormalizedRectResponse),
          ) as NormalizedRectResponse?;
          if (valueDes == null) continue;
          result.rect.replace(valueDes);
          break;
        case r'source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.source_ = valueDes;
          break;
        case r'submission_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.submissionId = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  AnnotationResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = AnnotationResponseBuilder();
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

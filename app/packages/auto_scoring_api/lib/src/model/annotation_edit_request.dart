//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'annotation_edit_request.g.dart';

/// One annotation to record as part of an ``edit`` request. Omitting the parent request's ``annotations`` field entirely (not sending an empty list) keeps the AI attempt's own marks -- see ``adapters.review_actions._carry_forward_annotations``.
///
/// Properties:
/// * [anchorText]
/// * [comment]
/// * [height]
/// * [kind]
/// * [width]
/// * [x]
/// * [y]
@BuiltValue()
abstract class AnnotationEditRequest
    implements Built<AnnotationEditRequest, AnnotationEditRequestBuilder> {
  @BuiltValueField(wireName: r'anchor_text')
  String? get anchorText;

  @BuiltValueField(wireName: r'comment')
  String? get comment;

  @BuiltValueField(wireName: r'height')
  num? get height;

  @BuiltValueField(wireName: r'kind')
  String get kind;

  @BuiltValueField(wireName: r'width')
  num? get width;

  @BuiltValueField(wireName: r'x')
  num? get x;

  @BuiltValueField(wireName: r'y')
  num? get y;

  AnnotationEditRequest._();

  factory AnnotationEditRequest(
      [void updates(AnnotationEditRequestBuilder b)]) = _$AnnotationEditRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(AnnotationEditRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<AnnotationEditRequest> get serializer =>
      _$AnnotationEditRequestSerializer();
}

class _$AnnotationEditRequestSerializer
    implements PrimitiveSerializer<AnnotationEditRequest> {
  @override
  final Iterable<Type> types = const [
    AnnotationEditRequest,
    _$AnnotationEditRequest
  ];

  @override
  final String wireName = r'AnnotationEditRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    AnnotationEditRequest object, {
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
    if (object.height != null) {
      yield r'height';
      yield serializers.serialize(
        object.height,
        specifiedType: const FullType.nullable(num),
      );
    }
    yield r'kind';
    yield serializers.serialize(
      object.kind,
      specifiedType: const FullType(String),
    );
    if (object.width != null) {
      yield r'width';
      yield serializers.serialize(
        object.width,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.x != null) {
      yield r'x';
      yield serializers.serialize(
        object.x,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.y != null) {
      yield r'y';
      yield serializers.serialize(
        object.y,
        specifiedType: const FullType.nullable(num),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    AnnotationEditRequest object, {
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
    required AnnotationEditRequestBuilder result,
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
        case r'height':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.height = valueDes;
          break;
        case r'kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.kind = valueDes;
          break;
        case r'width':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.width = valueDes;
          break;
        case r'x':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.x = valueDes;
          break;
        case r'y':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.y = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  AnnotationEditRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = AnnotationEditRequestBuilder();
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

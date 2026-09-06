//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'recognition_response_slim.g.dart';

/// The recognized-text row `edit_question` optionally creates. Deliberately not the full `api.recognitions_router.RecognitionResponse` (no ``boxes``, no ``stage``): a human's manually-entered correction never carries OCR word boxes, and this is always ``source=human`` by construction.
///
/// Properties:
/// * [confidence]
/// * [createdAt]
/// * [id]
/// * [text]
@BuiltValue()
abstract class RecognitionResponseSlim
    implements Built<RecognitionResponseSlim, RecognitionResponseSlimBuilder> {
  @BuiltValueField(wireName: r'confidence')
  num get confidence;

  @BuiltValueField(wireName: r'created_at')
  DateTime get createdAt;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'text')
  String get text;

  RecognitionResponseSlim._();

  factory RecognitionResponseSlim(
          [void updates(RecognitionResponseSlimBuilder b)]) =
      _$RecognitionResponseSlim;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(RecognitionResponseSlimBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<RecognitionResponseSlim> get serializer =>
      _$RecognitionResponseSlimSerializer();
}

class _$RecognitionResponseSlimSerializer
    implements PrimitiveSerializer<RecognitionResponseSlim> {
  @override
  final Iterable<Type> types = const [
    RecognitionResponseSlim,
    _$RecognitionResponseSlim
  ];

  @override
  final String wireName = r'RecognitionResponseSlim';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    RecognitionResponseSlim object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'confidence';
    yield serializers.serialize(
      object.confidence,
      specifiedType: const FullType(num),
    );
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
    yield r'text';
    yield serializers.serialize(
      object.text,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    RecognitionResponseSlim object, {
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
    required RecognitionResponseSlimBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'confidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.confidence = valueDes;
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
        case r'text':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.text = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  RecognitionResponseSlim deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = RecognitionResponseSlimBuilder();
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

//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'manual_recognition_request.g.dart';

/// ManualRecognitionRequest
///
/// Properties:
/// * [text]
@BuiltValue()
abstract class ManualRecognitionRequest
    implements
        Built<ManualRecognitionRequest, ManualRecognitionRequestBuilder> {
  @BuiltValueField(wireName: r'text')
  String get text;

  ManualRecognitionRequest._();

  factory ManualRecognitionRequest(
          [void updates(ManualRecognitionRequestBuilder b)]) =
      _$ManualRecognitionRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ManualRecognitionRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ManualRecognitionRequest> get serializer =>
      _$ManualRecognitionRequestSerializer();
}

class _$ManualRecognitionRequestSerializer
    implements PrimitiveSerializer<ManualRecognitionRequest> {
  @override
  final Iterable<Type> types = const [
    ManualRecognitionRequest,
    _$ManualRecognitionRequest
  ];

  @override
  final String wireName = r'ManualRecognitionRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ManualRecognitionRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'text';
    yield serializers.serialize(
      object.text,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ManualRecognitionRequest object, {
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
    required ManualRecognitionRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
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
  ManualRecognitionRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ManualRecognitionRequestBuilder();
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

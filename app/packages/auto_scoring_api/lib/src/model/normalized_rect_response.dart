//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'normalized_rect_response.g.dart';

/// NormalizedRectResponse
///
/// Properties:
/// * [height]
/// * [width]
/// * [x]
/// * [y]
@BuiltValue()
abstract class NormalizedRectResponse
    implements Built<NormalizedRectResponse, NormalizedRectResponseBuilder> {
  @BuiltValueField(wireName: r'height')
  num get height;

  @BuiltValueField(wireName: r'width')
  num get width;

  @BuiltValueField(wireName: r'x')
  num get x;

  @BuiltValueField(wireName: r'y')
  num get y;

  NormalizedRectResponse._();

  factory NormalizedRectResponse(
          [void updates(NormalizedRectResponseBuilder b)]) =
      _$NormalizedRectResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(NormalizedRectResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<NormalizedRectResponse> get serializer =>
      _$NormalizedRectResponseSerializer();
}

class _$NormalizedRectResponseSerializer
    implements PrimitiveSerializer<NormalizedRectResponse> {
  @override
  final Iterable<Type> types = const [
    NormalizedRectResponse,
    _$NormalizedRectResponse
  ];

  @override
  final String wireName = r'NormalizedRectResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    NormalizedRectResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'height';
    yield serializers.serialize(
      object.height,
      specifiedType: const FullType(num),
    );
    yield r'width';
    yield serializers.serialize(
      object.width,
      specifiedType: const FullType(num),
    );
    yield r'x';
    yield serializers.serialize(
      object.x,
      specifiedType: const FullType(num),
    );
    yield r'y';
    yield serializers.serialize(
      object.y,
      specifiedType: const FullType(num),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    NormalizedRectResponse object, {
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
    required NormalizedRectResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'height':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.height = valueDes;
          break;
        case r'width':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.width = valueDes;
          break;
        case r'x':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.x = valueDes;
          break;
        case r'y':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
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
  NormalizedRectResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = NormalizedRectResponseBuilder();
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

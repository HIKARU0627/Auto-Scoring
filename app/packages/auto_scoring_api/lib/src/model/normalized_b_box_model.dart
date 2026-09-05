//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'normalized_b_box_model.g.dart';

/// NormalizedBBoxModel
///
/// Properties:
/// * [x0]
/// * [x1]
/// * [y0]
/// * [y1]
@BuiltValue()
abstract class NormalizedBBoxModel
    implements Built<NormalizedBBoxModel, NormalizedBBoxModelBuilder> {
  @BuiltValueField(wireName: r'x0')
  num get x0;

  @BuiltValueField(wireName: r'x1')
  num get x1;

  @BuiltValueField(wireName: r'y0')
  num get y0;

  @BuiltValueField(wireName: r'y1')
  num get y1;

  NormalizedBBoxModel._();

  factory NormalizedBBoxModel([void updates(NormalizedBBoxModelBuilder b)]) =
      _$NormalizedBBoxModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(NormalizedBBoxModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<NormalizedBBoxModel> get serializer =>
      _$NormalizedBBoxModelSerializer();
}

class _$NormalizedBBoxModelSerializer
    implements PrimitiveSerializer<NormalizedBBoxModel> {
  @override
  final Iterable<Type> types = const [
    NormalizedBBoxModel,
    _$NormalizedBBoxModel
  ];

  @override
  final String wireName = r'NormalizedBBoxModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    NormalizedBBoxModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'x0';
    yield serializers.serialize(
      object.x0,
      specifiedType: const FullType(num),
    );
    yield r'x1';
    yield serializers.serialize(
      object.x1,
      specifiedType: const FullType(num),
    );
    yield r'y0';
    yield serializers.serialize(
      object.y0,
      specifiedType: const FullType(num),
    );
    yield r'y1';
    yield serializers.serialize(
      object.y1,
      specifiedType: const FullType(num),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    NormalizedBBoxModel object, {
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
    required NormalizedBBoxModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'x0':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.x0 = valueDes;
          break;
        case r'x1':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.x1 = valueDes;
          break;
        case r'y0':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.y0 = valueDes;
          break;
        case r'y1':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.y1 = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  NormalizedBBoxModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = NormalizedBBoxModelBuilder();
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

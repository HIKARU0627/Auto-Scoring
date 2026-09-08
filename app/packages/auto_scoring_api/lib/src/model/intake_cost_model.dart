//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'intake_cost_model.g.dart';

/// The per-call price the reviewer entered, or ``null`` for \"not set\".  ``null`` is not zero. Zero is a reviewer stating their usage is free; null is this app admitting it does not know the price and will say so on screen rather than showing an invented figure.
///
/// Properties:
/// * [classificationUnitCost]
@BuiltValue()
abstract class IntakeCostModel
    implements Built<IntakeCostModel, IntakeCostModelBuilder> {
  @BuiltValueField(wireName: r'classification_unit_cost')
  num? get classificationUnitCost;

  IntakeCostModel._();

  factory IntakeCostModel([void updates(IntakeCostModelBuilder b)]) =
      _$IntakeCostModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(IntakeCostModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<IntakeCostModel> get serializer =>
      _$IntakeCostModelSerializer();
}

class _$IntakeCostModelSerializer
    implements PrimitiveSerializer<IntakeCostModel> {
  @override
  final Iterable<Type> types = const [IntakeCostModel, _$IntakeCostModel];

  @override
  final String wireName = r'IntakeCostModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    IntakeCostModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.classificationUnitCost != null) {
      yield r'classification_unit_cost';
      yield serializers.serialize(
        object.classificationUnitCost,
        specifiedType: const FullType.nullable(num),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    IntakeCostModel object, {
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
    required IntakeCostModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'classification_unit_cost':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.classificationUnitCost = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  IntakeCostModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = IntakeCostModelBuilder();
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

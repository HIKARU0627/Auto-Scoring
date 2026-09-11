//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'grading_cost_model.g.dart';

/// Per-1000-token unit price, or ``null`` when not set.
///
/// Properties:
/// * [tokenUnitCost]
@BuiltValue()
abstract class GradingCostModel
    implements Built<GradingCostModel, GradingCostModelBuilder> {
  @BuiltValueField(wireName: r'token_unit_cost')
  num? get tokenUnitCost;

  GradingCostModel._();

  factory GradingCostModel([void updates(GradingCostModelBuilder b)]) =
      _$GradingCostModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(GradingCostModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<GradingCostModel> get serializer =>
      _$GradingCostModelSerializer();
}

class _$GradingCostModelSerializer
    implements PrimitiveSerializer<GradingCostModel> {
  @override
  final Iterable<Type> types = const [GradingCostModel, _$GradingCostModel];

  @override
  final String wireName = r'GradingCostModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    GradingCostModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.tokenUnitCost != null) {
      yield r'token_unit_cost';
      yield serializers.serialize(
        object.tokenUnitCost,
        specifiedType: const FullType.nullable(num),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    GradingCostModel object, {
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
    required GradingCostModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'token_unit_cost':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.tokenUnitCost = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  GradingCostModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = GradingCostModelBuilder();
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

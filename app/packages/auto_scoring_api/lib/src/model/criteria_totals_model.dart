//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'criteria_totals_model.g.dart';

/// The sum, the unknown count, and the comparison with the document's own stated total.  A snapshot of what is **saved**. The screen recomputes all of it from whatever the reviewer has typed but not yet saved -- showing this value beside unsaved edits would report a total for a list that is no longer on screen, the same trap ``test_settings_page.dart`` already avoids for the dependency graph's execution layers.
///
/// Properties:
/// * [declaredDifference]
/// * [declaredTotalPoints]
/// * [isComplete]
/// * [knownPoints]
/// * [unknownCount]
@BuiltValue()
abstract class CriteriaTotalsModel
    implements Built<CriteriaTotalsModel, CriteriaTotalsModelBuilder> {
  @BuiltValueField(wireName: r'declared_difference')
  int? get declaredDifference;

  @BuiltValueField(wireName: r'declared_total_points')
  int? get declaredTotalPoints;

  @BuiltValueField(wireName: r'is_complete')
  bool get isComplete;

  @BuiltValueField(wireName: r'known_points')
  int get knownPoints;

  @BuiltValueField(wireName: r'unknown_count')
  int get unknownCount;

  CriteriaTotalsModel._();

  factory CriteriaTotalsModel([void updates(CriteriaTotalsModelBuilder b)]) =
      _$CriteriaTotalsModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CriteriaTotalsModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CriteriaTotalsModel> get serializer =>
      _$CriteriaTotalsModelSerializer();
}

class _$CriteriaTotalsModelSerializer
    implements PrimitiveSerializer<CriteriaTotalsModel> {
  @override
  final Iterable<Type> types = const [
    CriteriaTotalsModel,
    _$CriteriaTotalsModel
  ];

  @override
  final String wireName = r'CriteriaTotalsModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CriteriaTotalsModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.declaredDifference != null) {
      yield r'declared_difference';
      yield serializers.serialize(
        object.declaredDifference,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.declaredTotalPoints != null) {
      yield r'declared_total_points';
      yield serializers.serialize(
        object.declaredTotalPoints,
        specifiedType: const FullType.nullable(int),
      );
    }
    yield r'is_complete';
    yield serializers.serialize(
      object.isComplete,
      specifiedType: const FullType(bool),
    );
    yield r'known_points';
    yield serializers.serialize(
      object.knownPoints,
      specifiedType: const FullType(int),
    );
    yield r'unknown_count';
    yield serializers.serialize(
      object.unknownCount,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CriteriaTotalsModel object, {
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
    required CriteriaTotalsModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'declared_difference':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.declaredDifference = valueDes;
          break;
        case r'declared_total_points':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.declaredTotalPoints = valueDes;
          break;
        case r'is_complete':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.isComplete = valueDes;
          break;
        case r'known_points':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.knownPoints = valueDes;
          break;
        case r'unknown_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.unknownCount = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CriteriaTotalsModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CriteriaTotalsModelBuilder();
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

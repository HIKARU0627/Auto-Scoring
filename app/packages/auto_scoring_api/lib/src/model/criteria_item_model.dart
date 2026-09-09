//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/criterion_kind.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'criteria_item_model.g.dart';

/// One marking criterion, over the wire.
///
/// Properties:
/// * [description]
/// * [kind]
/// * [points]
@BuiltValue()
abstract class CriteriaItemModel
    implements Built<CriteriaItemModel, CriteriaItemModelBuilder> {
  @BuiltValueField(wireName: r'description')
  String get description;

  @BuiltValueField(wireName: r'kind')
  CriterionKind get kind;
  // enum kindEnum {  add,  deduct,  };

  @BuiltValueField(wireName: r'points')
  int? get points;

  CriteriaItemModel._();

  factory CriteriaItemModel([void updates(CriteriaItemModelBuilder b)]) =
      _$CriteriaItemModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CriteriaItemModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CriteriaItemModel> get serializer =>
      _$CriteriaItemModelSerializer();
}

class _$CriteriaItemModelSerializer
    implements PrimitiveSerializer<CriteriaItemModel> {
  @override
  final Iterable<Type> types = const [CriteriaItemModel, _$CriteriaItemModel];

  @override
  final String wireName = r'CriteriaItemModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CriteriaItemModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'description';
    yield serializers.serialize(
      object.description,
      specifiedType: const FullType(String),
    );
    yield r'kind';
    yield serializers.serialize(
      object.kind,
      specifiedType: const FullType(CriterionKind),
    );
    if (object.points != null) {
      yield r'points';
      yield serializers.serialize(
        object.points,
        specifiedType: const FullType.nullable(int),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    CriteriaItemModel object, {
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
    required CriteriaItemModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'description':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.description = valueDes;
          break;
        case r'kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(CriterionKind),
          ) as CriterionKind;
          result.kind = valueDes;
          break;
        case r'points':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.points = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CriteriaItemModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CriteriaItemModelBuilder();
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

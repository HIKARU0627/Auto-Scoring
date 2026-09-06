//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/normalized_b_box_model.dart';
import 'package:auto_scoring_api/src/model/region_kind.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'region_model.g.dart';

/// RegionModel
///
/// Properties:
/// * [bbox]
/// * [confirmed]
/// * [kind]
/// * [label]
/// * [pageIndex]
/// * [regionId]
/// * [text]
@BuiltValue()
abstract class RegionModel implements Built<RegionModel, RegionModelBuilder> {
  @BuiltValueField(wireName: r'bbox')
  NormalizedBBoxModel get bbox;

  @BuiltValueField(wireName: r'confirmed')
  bool? get confirmed;

  @BuiltValueField(wireName: r'kind')
  RegionKind get kind;
  // enum kindEnum {  question,  answer_area,  annotation_area,  score,  rubric,  model_answer,  };

  @BuiltValueField(wireName: r'label')
  String get label;

  @BuiltValueField(wireName: r'page_index')
  int get pageIndex;

  @BuiltValueField(wireName: r'region_id')
  String get regionId;

  @BuiltValueField(wireName: r'text')
  String? get text;

  RegionModel._();

  factory RegionModel([void updates(RegionModelBuilder b)]) = _$RegionModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(RegionModelBuilder b) => b..confirmed = false;

  @BuiltValueSerializer(custom: true)
  static Serializer<RegionModel> get serializer => _$RegionModelSerializer();
}

class _$RegionModelSerializer implements PrimitiveSerializer<RegionModel> {
  @override
  final Iterable<Type> types = const [RegionModel, _$RegionModel];

  @override
  final String wireName = r'RegionModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    RegionModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'bbox';
    yield serializers.serialize(
      object.bbox,
      specifiedType: const FullType(NormalizedBBoxModel),
    );
    if (object.confirmed != null) {
      yield r'confirmed';
      yield serializers.serialize(
        object.confirmed,
        specifiedType: const FullType(bool),
      );
    }
    yield r'kind';
    yield serializers.serialize(
      object.kind,
      specifiedType: const FullType(RegionKind),
    );
    yield r'label';
    yield serializers.serialize(
      object.label,
      specifiedType: const FullType(String),
    );
    yield r'page_index';
    yield serializers.serialize(
      object.pageIndex,
      specifiedType: const FullType(int),
    );
    yield r'region_id';
    yield serializers.serialize(
      object.regionId,
      specifiedType: const FullType(String),
    );
    if (object.text != null) {
      yield r'text';
      yield serializers.serialize(
        object.text,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    RegionModel object, {
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
    required RegionModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'bbox':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(NormalizedBBoxModel),
          ) as NormalizedBBoxModel;
          result.bbox.replace(valueDes);
          break;
        case r'confirmed':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.confirmed = valueDes;
          break;
        case r'kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(RegionKind),
          ) as RegionKind;
          result.kind = valueDes;
          break;
        case r'label':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.label = valueDes;
          break;
        case r'page_index':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.pageIndex = valueDes;
          break;
        case r'region_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.regionId = valueDes;
          break;
        case r'text':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
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
  RegionModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = RegionModelBuilder();
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

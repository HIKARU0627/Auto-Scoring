//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/material_role.dart';
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/planned_file_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'planned_group_model.g.dart';

/// PlannedGroupModel
///
/// Properties:
/// * [files]
/// * [key]
/// * [missingRequiredRolesIfNew]
/// * [suggestedName]
@BuiltValue()
abstract class PlannedGroupModel
    implements Built<PlannedGroupModel, PlannedGroupModelBuilder> {
  @BuiltValueField(wireName: r'files')
  BuiltList<PlannedFileModel> get files;

  @BuiltValueField(wireName: r'key')
  String get key;

  @BuiltValueField(wireName: r'missing_required_roles_if_new')
  BuiltList<MaterialRole> get missingRequiredRolesIfNew;

  @BuiltValueField(wireName: r'suggested_name')
  String get suggestedName;

  PlannedGroupModel._();

  factory PlannedGroupModel([void updates(PlannedGroupModelBuilder b)]) =
      _$PlannedGroupModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(PlannedGroupModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<PlannedGroupModel> get serializer =>
      _$PlannedGroupModelSerializer();
}

class _$PlannedGroupModelSerializer
    implements PrimitiveSerializer<PlannedGroupModel> {
  @override
  final Iterable<Type> types = const [PlannedGroupModel, _$PlannedGroupModel];

  @override
  final String wireName = r'PlannedGroupModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    PlannedGroupModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'files';
    yield serializers.serialize(
      object.files,
      specifiedType: const FullType(BuiltList, [FullType(PlannedFileModel)]),
    );
    yield r'key';
    yield serializers.serialize(
      object.key,
      specifiedType: const FullType(String),
    );
    yield r'missing_required_roles_if_new';
    yield serializers.serialize(
      object.missingRequiredRolesIfNew,
      specifiedType: const FullType(BuiltList, [FullType(MaterialRole)]),
    );
    yield r'suggested_name';
    yield serializers.serialize(
      object.suggestedName,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    PlannedGroupModel object, {
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
    required PlannedGroupModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'files':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(PlannedFileModel)]),
          ) as BuiltList<PlannedFileModel>;
          result.files.replace(valueDes);
          break;
        case r'key':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.key = valueDes;
          break;
        case r'missing_required_roles_if_new':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(MaterialRole)]),
          ) as BuiltList<MaterialRole>;
          result.missingRequiredRolesIfNew.replace(valueDes);
          break;
        case r'suggested_name':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.suggestedName = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  PlannedGroupModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = PlannedGroupModelBuilder();
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

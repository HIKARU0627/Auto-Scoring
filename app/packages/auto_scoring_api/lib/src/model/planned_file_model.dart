//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/material_role.dart';
import 'package:auto_scoring_api/src/model/classification_need.dart';
import 'package:auto_scoring_api/src/model/role_source.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'planned_file_model.g.dart';

/// PlannedFileModel
///
/// Properties:
/// * [classification]
/// * [relativePath]
/// * [role]
/// * [roleSource]
/// * [sha256]
/// * [sizeBytes]
@BuiltValue()
abstract class PlannedFileModel
    implements Built<PlannedFileModel, PlannedFileModelBuilder> {
  @BuiltValueField(wireName: r'classification')
  ClassificationNeed get classification;
  // enum classificationEnum {  not_needed,  pending,  cached,  unsupported,  };

  @BuiltValueField(wireName: r'relative_path')
  String get relativePath;

  @BuiltValueField(wireName: r'role')
  MaterialRole? get role;
  // enum roleEnum {  student_answer,  grading_criteria,  annotation_resource,  annotation_sample,  reference,  ignore,  };

  @BuiltValueField(wireName: r'role_source')
  RoleSource get roleSource;
  // enum roleSourceEnum {  rule,  llm,  human,  unresolved,  };

  @BuiltValueField(wireName: r'sha256')
  String get sha256;

  @BuiltValueField(wireName: r'size_bytes')
  int get sizeBytes;

  PlannedFileModel._();

  factory PlannedFileModel([void updates(PlannedFileModelBuilder b)]) =
      _$PlannedFileModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(PlannedFileModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<PlannedFileModel> get serializer =>
      _$PlannedFileModelSerializer();
}

class _$PlannedFileModelSerializer
    implements PrimitiveSerializer<PlannedFileModel> {
  @override
  final Iterable<Type> types = const [PlannedFileModel, _$PlannedFileModel];

  @override
  final String wireName = r'PlannedFileModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    PlannedFileModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'classification';
    yield serializers.serialize(
      object.classification,
      specifiedType: const FullType(ClassificationNeed),
    );
    yield r'relative_path';
    yield serializers.serialize(
      object.relativePath,
      specifiedType: const FullType(String),
    );
    yield r'role';
    yield object.role == null
        ? null
        : serializers.serialize(
            object.role,
            specifiedType: const FullType.nullable(MaterialRole),
          );
    yield r'role_source';
    yield serializers.serialize(
      object.roleSource,
      specifiedType: const FullType(RoleSource),
    );
    yield r'sha256';
    yield serializers.serialize(
      object.sha256,
      specifiedType: const FullType(String),
    );
    yield r'size_bytes';
    yield serializers.serialize(
      object.sizeBytes,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    PlannedFileModel object, {
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
    required PlannedFileModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'classification':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(ClassificationNeed),
          ) as ClassificationNeed;
          result.classification = valueDes;
          break;
        case r'relative_path':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.relativePath = valueDes;
          break;
        case r'role':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(MaterialRole),
          ) as MaterialRole?;
          if (valueDes == null) continue;
          result.role = valueDes;
          break;
        case r'role_source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(RoleSource),
          ) as RoleSource;
          result.roleSource = valueDes;
          break;
        case r'sha256':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.sha256 = valueDes;
          break;
        case r'size_bytes':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.sizeBytes = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  PlannedFileModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = PlannedFileModelBuilder();
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

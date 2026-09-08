// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'material_role.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const MaterialRole _$studentAnswer = const MaterialRole._('studentAnswer');
const MaterialRole _$gradingCriteria = const MaterialRole._('gradingCriteria');
const MaterialRole _$annotationResource =
    const MaterialRole._('annotationResource');
const MaterialRole _$annotationSample =
    const MaterialRole._('annotationSample');
const MaterialRole _$reference = const MaterialRole._('reference');
const MaterialRole _$ignore = const MaterialRole._('ignore');

MaterialRole _$valueOf(String name) {
  switch (name) {
    case 'studentAnswer':
      return _$studentAnswer;
    case 'gradingCriteria':
      return _$gradingCriteria;
    case 'annotationResource':
      return _$annotationResource;
    case 'annotationSample':
      return _$annotationSample;
    case 'reference':
      return _$reference;
    case 'ignore':
      return _$ignore;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<MaterialRole> _$values =
    BuiltSet<MaterialRole>(const <MaterialRole>[
  _$studentAnswer,
  _$gradingCriteria,
  _$annotationResource,
  _$annotationSample,
  _$reference,
  _$ignore,
]);

class _$MaterialRoleMeta {
  const _$MaterialRoleMeta();
  MaterialRole get studentAnswer => _$studentAnswer;
  MaterialRole get gradingCriteria => _$gradingCriteria;
  MaterialRole get annotationResource => _$annotationResource;
  MaterialRole get annotationSample => _$annotationSample;
  MaterialRole get reference => _$reference;
  MaterialRole get ignore => _$ignore;
  MaterialRole valueOf(String name) => _$valueOf(name);
  BuiltSet<MaterialRole> get values => _$values;
}

abstract class _$MaterialRoleMixin {
  // ignore: non_constant_identifier_names
  _$MaterialRoleMeta get MaterialRole => const _$MaterialRoleMeta();
}

Serializer<MaterialRole> _$materialRoleSerializer = _$MaterialRoleSerializer();

class _$MaterialRoleSerializer implements PrimitiveSerializer<MaterialRole> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'studentAnswer': 'student_answer',
    'gradingCriteria': 'grading_criteria',
    'annotationResource': 'annotation_resource',
    'annotationSample': 'annotation_sample',
    'reference': 'reference',
    'ignore': 'ignore',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'student_answer': 'studentAnswer',
    'grading_criteria': 'gradingCriteria',
    'annotation_resource': 'annotationResource',
    'annotation_sample': 'annotationSample',
    'reference': 'reference',
    'ignore': 'ignore',
  };

  @override
  final Iterable<Type> types = const <Type>[MaterialRole];
  @override
  final String wireName = 'MaterialRole';

  @override
  Object serialize(Serializers serializers, MaterialRole object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  MaterialRole deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      MaterialRole.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

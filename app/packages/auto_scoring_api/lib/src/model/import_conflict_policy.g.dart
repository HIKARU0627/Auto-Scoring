// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'import_conflict_policy.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const ImportConflictPolicy _$keepEdited =
    const ImportConflictPolicy._('keepEdited');
const ImportConflictPolicy _$overwrite =
    const ImportConflictPolicy._('overwrite');

ImportConflictPolicy _$valueOf(String name) {
  switch (name) {
    case 'keepEdited':
      return _$keepEdited;
    case 'overwrite':
      return _$overwrite;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<ImportConflictPolicy> _$values =
    BuiltSet<ImportConflictPolicy>(const <ImportConflictPolicy>[
  _$keepEdited,
  _$overwrite,
]);

class _$ImportConflictPolicyMeta {
  const _$ImportConflictPolicyMeta();
  ImportConflictPolicy get keepEdited => _$keepEdited;
  ImportConflictPolicy get overwrite => _$overwrite;
  ImportConflictPolicy valueOf(String name) => _$valueOf(name);
  BuiltSet<ImportConflictPolicy> get values => _$values;
}

abstract class _$ImportConflictPolicyMixin {
  // ignore: non_constant_identifier_names
  _$ImportConflictPolicyMeta get ImportConflictPolicy =>
      const _$ImportConflictPolicyMeta();
}

Serializer<ImportConflictPolicy> _$importConflictPolicySerializer =
    _$ImportConflictPolicySerializer();

class _$ImportConflictPolicySerializer
    implements PrimitiveSerializer<ImportConflictPolicy> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'keepEdited': 'keep_edited',
    'overwrite': 'overwrite',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'keep_edited': 'keepEdited',
    'overwrite': 'overwrite',
  };

  @override
  final Iterable<Type> types = const <Type>[ImportConflictPolicy];
  @override
  final String wireName = 'ImportConflictPolicy';

  @override
  Object serialize(Serializers serializers, ImportConflictPolicy object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  ImportConflictPolicy deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      ImportConflictPolicy.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

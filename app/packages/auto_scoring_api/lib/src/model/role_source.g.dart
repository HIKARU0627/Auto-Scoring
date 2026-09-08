// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'role_source.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const RoleSource _$rule = const RoleSource._('rule');
const RoleSource _$llm = const RoleSource._('llm');
const RoleSource _$human = const RoleSource._('human');
const RoleSource _$unresolved = const RoleSource._('unresolved');

RoleSource _$valueOf(String name) {
  switch (name) {
    case 'rule':
      return _$rule;
    case 'llm':
      return _$llm;
    case 'human':
      return _$human;
    case 'unresolved':
      return _$unresolved;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<RoleSource> _$values = BuiltSet<RoleSource>(const <RoleSource>[
  _$rule,
  _$llm,
  _$human,
  _$unresolved,
]);

class _$RoleSourceMeta {
  const _$RoleSourceMeta();
  RoleSource get rule => _$rule;
  RoleSource get llm => _$llm;
  RoleSource get human => _$human;
  RoleSource get unresolved => _$unresolved;
  RoleSource valueOf(String name) => _$valueOf(name);
  BuiltSet<RoleSource> get values => _$values;
}

abstract class _$RoleSourceMixin {
  // ignore: non_constant_identifier_names
  _$RoleSourceMeta get RoleSource => const _$RoleSourceMeta();
}

Serializer<RoleSource> _$roleSourceSerializer = _$RoleSourceSerializer();

class _$RoleSourceSerializer implements PrimitiveSerializer<RoleSource> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'rule': 'rule',
    'llm': 'llm',
    'human': 'human',
    'unresolved': 'unresolved',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'rule': 'rule',
    'llm': 'llm',
    'human': 'human',
    'unresolved': 'unresolved',
  };

  @override
  final Iterable<Type> types = const <Type>[RoleSource];
  @override
  final String wireName = 'RoleSource';

  @override
  Object serialize(Serializers serializers, RoleSource object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  RoleSource deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      RoleSource.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

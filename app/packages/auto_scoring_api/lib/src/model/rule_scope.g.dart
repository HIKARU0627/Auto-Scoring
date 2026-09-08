// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'rule_scope.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const RuleScope _$file = const RuleScope._('file');
const RuleScope _$folder = const RuleScope._('folder');

RuleScope _$valueOf(String name) {
  switch (name) {
    case 'file':
      return _$file;
    case 'folder':
      return _$folder;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<RuleScope> _$values = BuiltSet<RuleScope>(const <RuleScope>[
  _$file,
  _$folder,
]);

class _$RuleScopeMeta {
  const _$RuleScopeMeta();
  RuleScope get file => _$file;
  RuleScope get folder => _$folder;
  RuleScope valueOf(String name) => _$valueOf(name);
  BuiltSet<RuleScope> get values => _$values;
}

abstract class _$RuleScopeMixin {
  // ignore: non_constant_identifier_names
  _$RuleScopeMeta get RuleScope => const _$RuleScopeMeta();
}

Serializer<RuleScope> _$ruleScopeSerializer = _$RuleScopeSerializer();

class _$RuleScopeSerializer implements PrimitiveSerializer<RuleScope> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'file': 'file',
    'folder': 'folder',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'file': 'file',
    'folder': 'folder',
  };

  @override
  final Iterable<Type> types = const <Type>[RuleScope];
  @override
  final String wireName = 'RuleScope';

  @override
  Object serialize(Serializers serializers, RuleScope object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  RuleScope deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      RuleScope.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

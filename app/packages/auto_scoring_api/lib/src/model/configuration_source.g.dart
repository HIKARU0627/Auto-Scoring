// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'configuration_source.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const ConfigurationSource _$credentialStore =
    const ConfigurationSource._('credentialStore');
const ConfigurationSource _$environment =
    const ConfigurationSource._('environment');
const ConfigurationSource _$builtinDefault =
    const ConfigurationSource._('builtinDefault');
const ConfigurationSource _$none = const ConfigurationSource._('none');

ConfigurationSource _$valueOf(String name) {
  switch (name) {
    case 'credentialStore':
      return _$credentialStore;
    case 'environment':
      return _$environment;
    case 'builtinDefault':
      return _$builtinDefault;
    case 'none':
      return _$none;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<ConfigurationSource> _$values =
    BuiltSet<ConfigurationSource>(const <ConfigurationSource>[
  _$credentialStore,
  _$environment,
  _$builtinDefault,
  _$none,
]);

class _$ConfigurationSourceMeta {
  const _$ConfigurationSourceMeta();
  ConfigurationSource get credentialStore => _$credentialStore;
  ConfigurationSource get environment => _$environment;
  ConfigurationSource get builtinDefault => _$builtinDefault;
  ConfigurationSource get none => _$none;
  ConfigurationSource valueOf(String name) => _$valueOf(name);
  BuiltSet<ConfigurationSource> get values => _$values;
}

abstract class _$ConfigurationSourceMixin {
  // ignore: non_constant_identifier_names
  _$ConfigurationSourceMeta get ConfigurationSource =>
      const _$ConfigurationSourceMeta();
}

Serializer<ConfigurationSource> _$configurationSourceSerializer =
    _$ConfigurationSourceSerializer();

class _$ConfigurationSourceSerializer
    implements PrimitiveSerializer<ConfigurationSource> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'credentialStore': 'credential_store',
    'environment': 'environment',
    'builtinDefault': 'builtin_default',
    'none': 'none',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'credential_store': 'credentialStore',
    'environment': 'environment',
    'builtin_default': 'builtinDefault',
    'none': 'none',
  };

  @override
  final Iterable<Type> types = const <Type>[ConfigurationSource];
  @override
  final String wireName = 'ConfigurationSource';

  @override
  Object serialize(Serializers serializers, ConfigurationSource object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  ConfigurationSource deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      ConfigurationSource.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

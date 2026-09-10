//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'configuration_source.g.dart';

/// Where an effective configuration value came from.
class ConfigurationSource extends EnumClass {
  @BuiltValueEnumConst(wireName: r'credential_store')
  static const ConfigurationSource credentialStore = _$credentialStore;
  @BuiltValueEnumConst(wireName: r'environment')
  static const ConfigurationSource environment = _$environment;
  @BuiltValueEnumConst(wireName: r'builtin_default')
  static const ConfigurationSource builtinDefault = _$builtinDefault;
  @BuiltValueEnumConst(wireName: r'none')
  static const ConfigurationSource none = _$none;

  static Serializer<ConfigurationSource> get serializer =>
      _$configurationSourceSerializer;

  const ConfigurationSource._(String name) : super(name);

  static BuiltSet<ConfigurationSource> get values => _$values;
  static ConfigurationSource valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class ConfigurationSourceMixin = Object
    with _$ConfigurationSourceMixin;

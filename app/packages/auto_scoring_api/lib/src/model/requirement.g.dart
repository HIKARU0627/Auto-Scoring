// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'requirement.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const Requirement _$required_ = const Requirement._('required_');
const Requirement _$recommended = const Requirement._('recommended');
const Requirement _$optional = const Requirement._('optional');

Requirement _$valueOf(String name) {
  switch (name) {
    case 'required_':
      return _$required_;
    case 'recommended':
      return _$recommended;
    case 'optional':
      return _$optional;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<Requirement> _$values =
    BuiltSet<Requirement>(const <Requirement>[
  _$required_,
  _$recommended,
  _$optional,
]);

class _$RequirementMeta {
  const _$RequirementMeta();
  Requirement get required_ => _$required_;
  Requirement get recommended => _$recommended;
  Requirement get optional => _$optional;
  Requirement valueOf(String name) => _$valueOf(name);
  BuiltSet<Requirement> get values => _$values;
}

abstract class _$RequirementMixin {
  // ignore: non_constant_identifier_names
  _$RequirementMeta get Requirement => const _$RequirementMeta();
}

Serializer<Requirement> _$requirementSerializer = _$RequirementSerializer();

class _$RequirementSerializer implements PrimitiveSerializer<Requirement> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'required_': 'required',
    'recommended': 'recommended',
    'optional': 'optional',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'required': 'required_',
    'recommended': 'recommended',
    'optional': 'optional',
  };

  @override
  final Iterable<Type> types = const <Type>[Requirement];
  @override
  final String wireName = 'Requirement';

  @override
  Object serialize(Serializers serializers, Requirement object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  Requirement deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      Requirement.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'usage_availability.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const UsageAvailability _$known = const UsageAvailability._('known');
const UsageAvailability _$partial = const UsageAvailability._('partial');
const UsageAvailability _$unknown = const UsageAvailability._('unknown');

UsageAvailability _$valueOf(String name) {
  switch (name) {
    case 'known':
      return _$known;
    case 'partial':
      return _$partial;
    case 'unknown':
      return _$unknown;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<UsageAvailability> _$values =
    BuiltSet<UsageAvailability>(const <UsageAvailability>[
  _$known,
  _$partial,
  _$unknown,
]);

class _$UsageAvailabilityMeta {
  const _$UsageAvailabilityMeta();
  UsageAvailability get known => _$known;
  UsageAvailability get partial => _$partial;
  UsageAvailability get unknown => _$unknown;
  UsageAvailability valueOf(String name) => _$valueOf(name);
  BuiltSet<UsageAvailability> get values => _$values;
}

abstract class _$UsageAvailabilityMixin {
  // ignore: non_constant_identifier_names
  _$UsageAvailabilityMeta get UsageAvailability =>
      const _$UsageAvailabilityMeta();
}

Serializer<UsageAvailability> _$usageAvailabilitySerializer =
    _$UsageAvailabilitySerializer();

class _$UsageAvailabilitySerializer
    implements PrimitiveSerializer<UsageAvailability> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'known': 'known',
    'partial': 'partial',
    'unknown': 'unknown',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'known': 'known',
    'partial': 'partial',
    'unknown': 'unknown',
  };

  @override
  final Iterable<Type> types = const <Type>[UsageAvailability];
  @override
  final String wireName = 'UsageAvailability';

  @override
  Object serialize(Serializers serializers, UsageAvailability object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  UsageAvailability deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      UsageAvailability.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

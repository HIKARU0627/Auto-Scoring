// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'dependency_provision.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const DependencyProvision _$recognizedText =
    const DependencyProvision._('recognizedText');
const DependencyProvision _$score = const DependencyProvision._('score');
const DependencyProvision _$criterionResult =
    const DependencyProvision._('criterionResult');

DependencyProvision _$valueOf(String name) {
  switch (name) {
    case 'recognizedText':
      return _$recognizedText;
    case 'score':
      return _$score;
    case 'criterionResult':
      return _$criterionResult;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<DependencyProvision> _$values =
    BuiltSet<DependencyProvision>(const <DependencyProvision>[
  _$recognizedText,
  _$score,
  _$criterionResult,
]);

class _$DependencyProvisionMeta {
  const _$DependencyProvisionMeta();
  DependencyProvision get recognizedText => _$recognizedText;
  DependencyProvision get score => _$score;
  DependencyProvision get criterionResult => _$criterionResult;
  DependencyProvision valueOf(String name) => _$valueOf(name);
  BuiltSet<DependencyProvision> get values => _$values;
}

abstract class _$DependencyProvisionMixin {
  // ignore: non_constant_identifier_names
  _$DependencyProvisionMeta get DependencyProvision =>
      const _$DependencyProvisionMeta();
}

Serializer<DependencyProvision> _$dependencyProvisionSerializer =
    _$DependencyProvisionSerializer();

class _$DependencyProvisionSerializer
    implements PrimitiveSerializer<DependencyProvision> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'recognizedText': 'recognized_text',
    'score': 'score',
    'criterionResult': 'criterion_result',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'recognized_text': 'recognizedText',
    'score': 'score',
    'criterion_result': 'criterionResult',
  };

  @override
  final Iterable<Type> types = const <Type>[DependencyProvision];
  @override
  final String wireName = 'DependencyProvision';

  @override
  Object serialize(Serializers serializers, DependencyProvision object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  DependencyProvision deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      DependencyProvision.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'classification_need.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const ClassificationNeed _$notNeeded = const ClassificationNeed._('notNeeded');
const ClassificationNeed _$pending = const ClassificationNeed._('pending');
const ClassificationNeed _$cached = const ClassificationNeed._('cached');
const ClassificationNeed _$unsupported =
    const ClassificationNeed._('unsupported');

ClassificationNeed _$valueOf(String name) {
  switch (name) {
    case 'notNeeded':
      return _$notNeeded;
    case 'pending':
      return _$pending;
    case 'cached':
      return _$cached;
    case 'unsupported':
      return _$unsupported;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<ClassificationNeed> _$values =
    BuiltSet<ClassificationNeed>(const <ClassificationNeed>[
  _$notNeeded,
  _$pending,
  _$cached,
  _$unsupported,
]);

class _$ClassificationNeedMeta {
  const _$ClassificationNeedMeta();
  ClassificationNeed get notNeeded => _$notNeeded;
  ClassificationNeed get pending => _$pending;
  ClassificationNeed get cached => _$cached;
  ClassificationNeed get unsupported => _$unsupported;
  ClassificationNeed valueOf(String name) => _$valueOf(name);
  BuiltSet<ClassificationNeed> get values => _$values;
}

abstract class _$ClassificationNeedMixin {
  // ignore: non_constant_identifier_names
  _$ClassificationNeedMeta get ClassificationNeed =>
      const _$ClassificationNeedMeta();
}

Serializer<ClassificationNeed> _$classificationNeedSerializer =
    _$ClassificationNeedSerializer();

class _$ClassificationNeedSerializer
    implements PrimitiveSerializer<ClassificationNeed> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'notNeeded': 'not_needed',
    'pending': 'pending',
    'cached': 'cached',
    'unsupported': 'unsupported',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'not_needed': 'notNeeded',
    'pending': 'pending',
    'cached': 'cached',
    'unsupported': 'unsupported',
  };

  @override
  final Iterable<Type> types = const <Type>[ClassificationNeed];
  @override
  final String wireName = 'ClassificationNeed';

  @override
  Object serialize(Serializers serializers, ClassificationNeed object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  ClassificationNeed deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      ClassificationNeed.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

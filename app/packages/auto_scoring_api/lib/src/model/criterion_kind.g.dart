// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'criterion_kind.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const CriterionKind _$add = const CriterionKind._('add');
const CriterionKind _$deduct = const CriterionKind._('deduct');

CriterionKind _$valueOf(String name) {
  switch (name) {
    case 'add':
      return _$add;
    case 'deduct':
      return _$deduct;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<CriterionKind> _$values =
    BuiltSet<CriterionKind>(const <CriterionKind>[
  _$add,
  _$deduct,
]);

class _$CriterionKindMeta {
  const _$CriterionKindMeta();
  CriterionKind get add => _$add;
  CriterionKind get deduct => _$deduct;
  CriterionKind valueOf(String name) => _$valueOf(name);
  BuiltSet<CriterionKind> get values => _$values;
}

abstract class _$CriterionKindMixin {
  // ignore: non_constant_identifier_names
  _$CriterionKindMeta get CriterionKind => const _$CriterionKindMeta();
}

Serializer<CriterionKind> _$criterionKindSerializer =
    _$CriterionKindSerializer();

class _$CriterionKindSerializer implements PrimitiveSerializer<CriterionKind> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'add': 'add',
    'deduct': 'deduct',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'add': 'add',
    'deduct': 'deduct',
  };

  @override
  final Iterable<Type> types = const <Type>[CriterionKind];
  @override
  final String wireName = 'CriterionKind';

  @override
  Object serialize(Serializers serializers, CriterionKind object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  CriterionKind deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      CriterionKind.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

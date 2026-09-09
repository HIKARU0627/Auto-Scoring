// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'criteria_status.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const CriteriaStatus _$draft = const CriteriaStatus._('draft');
const CriteriaStatus _$confirmed = const CriteriaStatus._('confirmed');

CriteriaStatus _$valueOf(String name) {
  switch (name) {
    case 'draft':
      return _$draft;
    case 'confirmed':
      return _$confirmed;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<CriteriaStatus> _$values =
    BuiltSet<CriteriaStatus>(const <CriteriaStatus>[
  _$draft,
  _$confirmed,
]);

class _$CriteriaStatusMeta {
  const _$CriteriaStatusMeta();
  CriteriaStatus get draft => _$draft;
  CriteriaStatus get confirmed => _$confirmed;
  CriteriaStatus valueOf(String name) => _$valueOf(name);
  BuiltSet<CriteriaStatus> get values => _$values;
}

abstract class _$CriteriaStatusMixin {
  // ignore: non_constant_identifier_names
  _$CriteriaStatusMeta get CriteriaStatus => const _$CriteriaStatusMeta();
}

Serializer<CriteriaStatus> _$criteriaStatusSerializer =
    _$CriteriaStatusSerializer();

class _$CriteriaStatusSerializer
    implements PrimitiveSerializer<CriteriaStatus> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'draft': 'draft',
    'confirmed': 'confirmed',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'draft': 'draft',
    'confirmed': 'confirmed',
  };

  @override
  final Iterable<Type> types = const <Type>[CriteriaStatus];
  @override
  final String wireName = 'CriteriaStatus';

  @override
  Object serialize(Serializers serializers, CriteriaStatus object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  CriteriaStatus deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      CriteriaStatus.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

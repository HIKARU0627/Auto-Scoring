// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'bulk_export_item_status.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const BulkExportItemStatus _$queued = const BulkExportItemStatus._('queued');
const BulkExportItemStatus _$reused = const BulkExportItemStatus._('reused');
const BulkExportItemStatus _$refused = const BulkExportItemStatus._('refused');

BulkExportItemStatus _$valueOf(String name) {
  switch (name) {
    case 'queued':
      return _$queued;
    case 'reused':
      return _$reused;
    case 'refused':
      return _$refused;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<BulkExportItemStatus> _$values =
    BuiltSet<BulkExportItemStatus>(const <BulkExportItemStatus>[
  _$queued,
  _$reused,
  _$refused,
]);

class _$BulkExportItemStatusMeta {
  const _$BulkExportItemStatusMeta();
  BulkExportItemStatus get queued => _$queued;
  BulkExportItemStatus get reused => _$reused;
  BulkExportItemStatus get refused => _$refused;
  BulkExportItemStatus valueOf(String name) => _$valueOf(name);
  BuiltSet<BulkExportItemStatus> get values => _$values;
}

abstract class _$BulkExportItemStatusMixin {
  // ignore: non_constant_identifier_names
  _$BulkExportItemStatusMeta get BulkExportItemStatus =>
      const _$BulkExportItemStatusMeta();
}

Serializer<BulkExportItemStatus> _$bulkExportItemStatusSerializer =
    _$BulkExportItemStatusSerializer();

class _$BulkExportItemStatusSerializer
    implements PrimitiveSerializer<BulkExportItemStatus> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'queued': 'queued',
    'reused': 'reused',
    'refused': 'refused',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'queued': 'queued',
    'reused': 'reused',
    'refused': 'refused',
  };

  @override
  final Iterable<Type> types = const <Type>[BulkExportItemStatus];
  @override
  final String wireName = 'BulkExportItemStatus';

  @override
  Object serialize(Serializers serializers, BulkExportItemStatus object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  BulkExportItemStatus deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      BulkExportItemStatus.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'export_refusal_reason.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const ExportRefusalReason _$unconfirmedQuestions =
    const ExportRefusalReason._('unconfirmedQuestions');
const ExportRefusalReason _$noRoomForScore =
    const ExportRefusalReason._('noRoomForScore');

ExportRefusalReason _$valueOf(String name) {
  switch (name) {
    case 'unconfirmedQuestions':
      return _$unconfirmedQuestions;
    case 'noRoomForScore':
      return _$noRoomForScore;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<ExportRefusalReason> _$values =
    BuiltSet<ExportRefusalReason>(const <ExportRefusalReason>[
  _$unconfirmedQuestions,
  _$noRoomForScore,
]);

class _$ExportRefusalReasonMeta {
  const _$ExportRefusalReasonMeta();
  ExportRefusalReason get unconfirmedQuestions => _$unconfirmedQuestions;
  ExportRefusalReason get noRoomForScore => _$noRoomForScore;
  ExportRefusalReason valueOf(String name) => _$valueOf(name);
  BuiltSet<ExportRefusalReason> get values => _$values;
}

abstract class _$ExportRefusalReasonMixin {
  // ignore: non_constant_identifier_names
  _$ExportRefusalReasonMeta get ExportRefusalReason =>
      const _$ExportRefusalReasonMeta();
}

Serializer<ExportRefusalReason> _$exportRefusalReasonSerializer =
    _$ExportRefusalReasonSerializer();

class _$ExportRefusalReasonSerializer
    implements PrimitiveSerializer<ExportRefusalReason> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'unconfirmedQuestions': 'unconfirmed_questions',
    'noRoomForScore': 'no_room_for_score',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'unconfirmed_questions': 'unconfirmedQuestions',
    'no_room_for_score': 'noRoomForScore',
  };

  @override
  final Iterable<Type> types = const <Type>[ExportRefusalReason];
  @override
  final String wireName = 'ExportRefusalReason';

  @override
  Object serialize(Serializers serializers, ExportRefusalReason object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  ExportRefusalReason deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      ExportRefusalReason.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'catalog_state.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const CatalogState _$notRegistered = const CatalogState._('notRegistered');
const CatalogState _$wordOnly = const CatalogState._('wordOnly');
const CatalogState _$unreadable = const CatalogState._('unreadable');
const CatalogState _$available = const CatalogState._('available');

CatalogState _$valueOf(String name) {
  switch (name) {
    case 'notRegistered':
      return _$notRegistered;
    case 'wordOnly':
      return _$wordOnly;
    case 'unreadable':
      return _$unreadable;
    case 'available':
      return _$available;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<CatalogState> _$values =
    BuiltSet<CatalogState>(const <CatalogState>[
  _$notRegistered,
  _$wordOnly,
  _$unreadable,
  _$available,
]);

class _$CatalogStateMeta {
  const _$CatalogStateMeta();
  CatalogState get notRegistered => _$notRegistered;
  CatalogState get wordOnly => _$wordOnly;
  CatalogState get unreadable => _$unreadable;
  CatalogState get available => _$available;
  CatalogState valueOf(String name) => _$valueOf(name);
  BuiltSet<CatalogState> get values => _$values;
}

abstract class _$CatalogStateMixin {
  // ignore: non_constant_identifier_names
  _$CatalogStateMeta get CatalogState => const _$CatalogStateMeta();
}

Serializer<CatalogState> _$catalogStateSerializer = _$CatalogStateSerializer();

class _$CatalogStateSerializer implements PrimitiveSerializer<CatalogState> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'notRegistered': 'not_registered',
    'wordOnly': 'word_only',
    'unreadable': 'unreadable',
    'available': 'available',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'not_registered': 'notRegistered',
    'word_only': 'wordOnly',
    'unreadable': 'unreadable',
    'available': 'available',
  };

  @override
  final Iterable<Type> types = const <Type>[CatalogState];
  @override
  final String wireName = 'CatalogState';

  @override
  Object serialize(Serializers serializers, CatalogState object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  CatalogState deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      CatalogState.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'catalog_state.g.dart';

/// Why a test has, or has not, a usable 誤答カタログ (Issue #209).  The three situations Issue #106's logging used to collapse into one are now three distinct wire values, because a person deciding what to do next needs to tell \"we never received the file\" from \"we received it and could not understand it\": the first means attach a 添削資料, the second means the one already attached is not a layout this reader knows.  ============================ ================================================ value                        meaning ============================ ================================================ ``not_registered``           no 添削資料 of any kind is attached (a) ``word_only``                a 添削資料 is attached, but none is .xls/.xlsx (b) ``unreadable``               an Excel 添削資料 is attached but yielded no entries (c) ``available``                entries were imported from the attached Excel ============================ ================================================
class CatalogState extends EnumClass {
  @BuiltValueEnumConst(wireName: r'not_registered')
  static const CatalogState notRegistered = _$notRegistered;
  @BuiltValueEnumConst(wireName: r'word_only')
  static const CatalogState wordOnly = _$wordOnly;
  @BuiltValueEnumConst(wireName: r'unreadable')
  static const CatalogState unreadable = _$unreadable;
  @BuiltValueEnumConst(wireName: r'available')
  static const CatalogState available = _$available;

  static Serializer<CatalogState> get serializer => _$catalogStateSerializer;

  const CatalogState._(String name) : super(name);

  static BuiltSet<CatalogState> get values => _$values;
  static CatalogState valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class CatalogStateMixin = Object with _$CatalogStateMixin;

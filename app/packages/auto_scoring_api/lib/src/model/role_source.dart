//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'role_source.g.dart';

/// Where a file's proposed role came from.  Rendered on the confirmation screen, because \"a rule matched this name\" and \"a model looked at the first page and guessed\" deserve different amounts of the reviewer's attention -- and :attr:`UNRESOLVED` deserves all of it.
class RoleSource extends EnumClass {
  @BuiltValueEnumConst(wireName: r'rule')
  static const RoleSource rule = _$rule;
  @BuiltValueEnumConst(wireName: r'llm')
  static const RoleSource llm = _$llm;
  @BuiltValueEnumConst(wireName: r'human')
  static const RoleSource human = _$human;
  @BuiltValueEnumConst(wireName: r'unresolved')
  static const RoleSource unresolved = _$unresolved;

  static Serializer<RoleSource> get serializer => _$roleSourceSerializer;

  const RoleSource._(String name) : super(name);

  static BuiltSet<RoleSource> get values => _$values;
  static RoleSource valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class RoleSourceMixin = Object with _$RoleSourceMixin;

//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'import_conflict_policy.g.dart';

/// What a re-import does with rows a person edited.  Required, never defaulted: a caller that has not decided must not get a choice made for it, because both choices lose something -- ``overwrite`` loses the edit, ``keep_edited`` can leave a stale row beside a fresh one.
class ImportConflictPolicy extends EnumClass {
  @BuiltValueEnumConst(wireName: r'keep_edited')
  static const ImportConflictPolicy keepEdited = _$keepEdited;
  @BuiltValueEnumConst(wireName: r'overwrite')
  static const ImportConflictPolicy overwrite = _$overwrite;

  static Serializer<ImportConflictPolicy> get serializer =>
      _$importConflictPolicySerializer;

  const ImportConflictPolicy._(String name) : super(name);

  static BuiltSet<ImportConflictPolicy> get values => _$values;
  static ImportConflictPolicy valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class ImportConflictPolicyMixin = Object
    with _$ImportConflictPolicyMixin;

//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'requirement.g.dart';

/// How badly a role is needed, for the confirmation screen's own warning.  Only :attr:`REQUIRED` is enforced, and only for a group that creates a *new* test -- a group that adds files to an already-registered test needs no grading criteria, because that test already has one (Issue #101, the second-week flow). The enforcement itself is not here: it is the ``POST /tests`` signature, which cannot be called without the criteria file at all (``AGENTS.md``: guarantee invariants with real constraints, not with UI state).
class Requirement extends EnumClass {
  @BuiltValueEnumConst(wireName: r'required')
  static const Requirement required_ = _$required_;
  @BuiltValueEnumConst(wireName: r'recommended')
  static const Requirement recommended = _$recommended;
  @BuiltValueEnumConst(wireName: r'optional')
  static const Requirement optional = _$optional;

  static Serializer<Requirement> get serializer => _$requirementSerializer;

  const Requirement._(String name) : super(name);

  static BuiltSet<Requirement> get values => _$values;
  static Requirement valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class RequirementMixin = Object with _$RequirementMixin;

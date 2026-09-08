//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'criterion_kind.g.dart';

/// Whether a criterion adds points or takes them away.  Both exist in the measured material: most subjects list what earns points, and at least one is written entirely as deductions from a full allocation. Collapsing the two into a signed number was rejected -- a reviewer editing \"-2\" cannot tell a deduction of 2 from a typo, and the grading prompt (``jobs.grading_processor._rubric_text_for``) has to say which it is.
class CriterionKind extends EnumClass {
  @BuiltValueEnumConst(wireName: r'add')
  static const CriterionKind add = _$add;
  @BuiltValueEnumConst(wireName: r'deduct')
  static const CriterionKind deduct = _$deduct;

  static Serializer<CriterionKind> get serializer => _$criterionKindSerializer;

  const CriterionKind._(String name) : super(name);

  static BuiltSet<CriterionKind> get values => _$values;
  static CriterionKind valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class CriterionKindMixin = Object with _$CriterionKindMixin;

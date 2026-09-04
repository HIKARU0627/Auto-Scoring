//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'dependency_provision.g.dart';

/// What a prerequisite question hands to its dependent (§9.2 result shape).
class DependencyProvision extends EnumClass {
  @BuiltValueEnumConst(wireName: r'recognized_text')
  static const DependencyProvision recognizedText = _$recognizedText;
  @BuiltValueEnumConst(wireName: r'score')
  static const DependencyProvision score = _$score;
  @BuiltValueEnumConst(wireName: r'criterion_result')
  static const DependencyProvision criterionResult = _$criterionResult;

  static Serializer<DependencyProvision> get serializer =>
      _$dependencyProvisionSerializer;

  const DependencyProvision._(String name) : super(name);

  static BuiltSet<DependencyProvision> get values => _$values;
  static DependencyProvision valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class DependencyProvisionMixin = Object
    with _$DependencyProvisionMixin;

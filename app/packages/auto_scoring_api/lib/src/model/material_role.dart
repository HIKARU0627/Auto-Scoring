//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'material_role.g.dart';

/// What one file is, once a human has confirmed it.  Mirrors the material kinds Issue #95 recorded for the real batches. Note what is *not* here: there is no \"model answer\" role. The model-answer PDF was dropped as a required input (Issue #95 decision 1) because it does not exist in the real material -- a model answer that happens to be on hand is imported as :attr:`REFERENCE`.
class MaterialRole extends EnumClass {
  @BuiltValueEnumConst(wireName: r'student_answer')
  static const MaterialRole studentAnswer = _$studentAnswer;
  @BuiltValueEnumConst(wireName: r'grading_criteria')
  static const MaterialRole gradingCriteria = _$gradingCriteria;
  @BuiltValueEnumConst(wireName: r'annotation_resource')
  static const MaterialRole annotationResource = _$annotationResource;
  @BuiltValueEnumConst(wireName: r'annotation_sample')
  static const MaterialRole annotationSample = _$annotationSample;
  @BuiltValueEnumConst(wireName: r'reference')
  static const MaterialRole reference = _$reference;
  @BuiltValueEnumConst(wireName: r'ignore')
  static const MaterialRole ignore = _$ignore;

  static Serializer<MaterialRole> get serializer => _$materialRoleSerializer;

  const MaterialRole._(String name) : super(name);

  static BuiltSet<MaterialRole> get values => _$values;
  static MaterialRole valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class MaterialRoleMixin = Object with _$MaterialRoleMixin;

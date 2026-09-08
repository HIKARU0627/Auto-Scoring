//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'classification_need.g.dart';

/// Whether this file would cost an LLM call, and if not, why not.  This is what makes the pre-flight \"how many calls, roughly how much\" number on the confirmation screen honest: each file lands in exactly one of these, and only :attr:`PENDING` is charged for.
class ClassificationNeed extends EnumClass {
  @BuiltValueEnumConst(wireName: r'not_needed')
  static const ClassificationNeed notNeeded = _$notNeeded;
  @BuiltValueEnumConst(wireName: r'pending')
  static const ClassificationNeed pending = _$pending;
  @BuiltValueEnumConst(wireName: r'cached')
  static const ClassificationNeed cached = _$cached;
  @BuiltValueEnumConst(wireName: r'unsupported')
  static const ClassificationNeed unsupported = _$unsupported;

  static Serializer<ClassificationNeed> get serializer =>
      _$classificationNeedSerializer;

  const ClassificationNeed._(String name) : super(name);

  static BuiltSet<ClassificationNeed> get values => _$values;
  static ClassificationNeed valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class ClassificationNeedMixin = Object with _$ClassificationNeedMixin;

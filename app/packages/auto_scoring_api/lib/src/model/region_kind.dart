//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'region_kind.g.dart';

class RegionKind extends EnumClass {
  @BuiltValueEnumConst(wireName: r'question')
  static const RegionKind question = _$question;
  @BuiltValueEnumConst(wireName: r'answer_area')
  static const RegionKind answerArea = _$answerArea;
  @BuiltValueEnumConst(wireName: r'annotation_area')
  static const RegionKind annotationArea = _$annotationArea;
  @BuiltValueEnumConst(wireName: r'score')
  static const RegionKind score = _$score;
  @BuiltValueEnumConst(wireName: r'rubric')
  static const RegionKind rubric = _$rubric;
  @BuiltValueEnumConst(wireName: r'model_answer')
  static const RegionKind modelAnswer = _$modelAnswer;

  static Serializer<RegionKind> get serializer => _$regionKindSerializer;

  const RegionKind._(String name) : super(name);

  static BuiltSet<RegionKind> get values => _$values;
  static RegionKind valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class RegionKindMixin = Object with _$RegionKindMixin;

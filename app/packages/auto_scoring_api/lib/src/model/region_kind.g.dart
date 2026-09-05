// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'region_kind.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const RegionKind _$question = const RegionKind._('question');
const RegionKind _$answerArea = const RegionKind._('answerArea');
const RegionKind _$annotationArea = const RegionKind._('annotationArea');
const RegionKind _$score = const RegionKind._('score');
const RegionKind _$rubric = const RegionKind._('rubric');
const RegionKind _$modelAnswer = const RegionKind._('modelAnswer');

RegionKind _$valueOf(String name) {
  switch (name) {
    case 'question':
      return _$question;
    case 'answerArea':
      return _$answerArea;
    case 'annotationArea':
      return _$annotationArea;
    case 'score':
      return _$score;
    case 'rubric':
      return _$rubric;
    case 'modelAnswer':
      return _$modelAnswer;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<RegionKind> _$values = BuiltSet<RegionKind>(const <RegionKind>[
  _$question,
  _$answerArea,
  _$annotationArea,
  _$score,
  _$rubric,
  _$modelAnswer,
]);

class _$RegionKindMeta {
  const _$RegionKindMeta();
  RegionKind get question => _$question;
  RegionKind get answerArea => _$answerArea;
  RegionKind get annotationArea => _$annotationArea;
  RegionKind get score => _$score;
  RegionKind get rubric => _$rubric;
  RegionKind get modelAnswer => _$modelAnswer;
  RegionKind valueOf(String name) => _$valueOf(name);
  BuiltSet<RegionKind> get values => _$values;
}

abstract class _$RegionKindMixin {
  // ignore: non_constant_identifier_names
  _$RegionKindMeta get RegionKind => const _$RegionKindMeta();
}

Serializer<RegionKind> _$regionKindSerializer = _$RegionKindSerializer();

class _$RegionKindSerializer implements PrimitiveSerializer<RegionKind> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'question': 'question',
    'answerArea': 'answer_area',
    'annotationArea': 'annotation_area',
    'score': 'score',
    'rubric': 'rubric',
    'modelAnswer': 'model_answer',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'question': 'question',
    'answer_area': 'answerArea',
    'annotation_area': 'annotationArea',
    'score': 'score',
    'rubric': 'rubric',
    'model_answer': 'modelAnswer',
  };

  @override
  final Iterable<Type> types = const <Type>[RegionKind];
  @override
  final String wireName = 'RegionKind';

  @override
  Object serialize(Serializers serializers, RegionKind object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  RegionKind deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      RegionKind.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

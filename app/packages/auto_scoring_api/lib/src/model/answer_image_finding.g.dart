// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'answer_image_finding.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

const AnswerImageFinding _$answer = const AnswerImageFinding._('answer');
const AnswerImageFinding _$blank = const AnswerImageFinding._('blank');
const AnswerImageFinding _$notTheAnswer =
    const AnswerImageFinding._('notTheAnswer');

AnswerImageFinding _$valueOf(String name) {
  switch (name) {
    case 'answer':
      return _$answer;
    case 'blank':
      return _$blank;
    case 'notTheAnswer':
      return _$notTheAnswer;
    default:
      throw ArgumentError(name);
  }
}

final BuiltSet<AnswerImageFinding> _$values =
    BuiltSet<AnswerImageFinding>(const <AnswerImageFinding>[
  _$answer,
  _$blank,
  _$notTheAnswer,
]);

class _$AnswerImageFindingMeta {
  const _$AnswerImageFindingMeta();
  AnswerImageFinding get answer => _$answer;
  AnswerImageFinding get blank => _$blank;
  AnswerImageFinding get notTheAnswer => _$notTheAnswer;
  AnswerImageFinding valueOf(String name) => _$valueOf(name);
  BuiltSet<AnswerImageFinding> get values => _$values;
}

abstract class _$AnswerImageFindingMixin {
  // ignore: non_constant_identifier_names
  _$AnswerImageFindingMeta get AnswerImageFinding =>
      const _$AnswerImageFindingMeta();
}

Serializer<AnswerImageFinding> _$answerImageFindingSerializer =
    _$AnswerImageFindingSerializer();

class _$AnswerImageFindingSerializer
    implements PrimitiveSerializer<AnswerImageFinding> {
  static const Map<String, Object> _toWire = const <String, Object>{
    'answer': 'answer',
    'blank': 'blank',
    'notTheAnswer': 'not_the_answer',
  };
  static const Map<Object, String> _fromWire = const <Object, String>{
    'answer': 'answer',
    'blank': 'blank',
    'not_the_answer': 'notTheAnswer',
  };

  @override
  final Iterable<Type> types = const <Type>[AnswerImageFinding];
  @override
  final String wireName = 'AnswerImageFinding';

  @override
  Object serialize(Serializers serializers, AnswerImageFinding object,
          {FullType specifiedType = FullType.unspecified}) =>
      _toWire[object.name] ?? object.name;

  @override
  AnswerImageFinding deserialize(Serializers serializers, Object serialized,
          {FullType specifiedType = FullType.unspecified}) =>
      AnswerImageFinding.valueOf(
          _fromWire[serialized] ?? (serialized is String ? serialized : ''));
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

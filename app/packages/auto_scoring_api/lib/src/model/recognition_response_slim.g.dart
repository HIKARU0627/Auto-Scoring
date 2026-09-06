// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'recognition_response_slim.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$RecognitionResponseSlim extends RecognitionResponseSlim {
  @override
  final num confidence;
  @override
  final DateTime createdAt;
  @override
  final String id;
  @override
  final String text;

  factory _$RecognitionResponseSlim(
          [void Function(RecognitionResponseSlimBuilder)? updates]) =>
      (RecognitionResponseSlimBuilder()..update(updates))._build();

  _$RecognitionResponseSlim._(
      {required this.confidence,
      required this.createdAt,
      required this.id,
      required this.text})
      : super._();
  @override
  RecognitionResponseSlim rebuild(
          void Function(RecognitionResponseSlimBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  RecognitionResponseSlimBuilder toBuilder() =>
      RecognitionResponseSlimBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is RecognitionResponseSlim &&
        confidence == other.confidence &&
        createdAt == other.createdAt &&
        id == other.id &&
        text == other.text;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, text.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'RecognitionResponseSlim')
          ..add('confidence', confidence)
          ..add('createdAt', createdAt)
          ..add('id', id)
          ..add('text', text))
        .toString();
  }
}

class RecognitionResponseSlimBuilder
    implements
        Builder<RecognitionResponseSlim, RecognitionResponseSlimBuilder> {
  _$RecognitionResponseSlim? _$v;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _text;
  String? get text => _$this._text;
  set text(String? text) => _$this._text = text;

  RecognitionResponseSlimBuilder() {
    RecognitionResponseSlim._defaults(this);
  }

  RecognitionResponseSlimBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _confidence = $v.confidence;
      _createdAt = $v.createdAt;
      _id = $v.id;
      _text = $v.text;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(RecognitionResponseSlim other) {
    _$v = other as _$RecognitionResponseSlim;
  }

  @override
  void update(void Function(RecognitionResponseSlimBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  RecognitionResponseSlim build() => _build();

  _$RecognitionResponseSlim _build() {
    final _$result = _$v ??
        _$RecognitionResponseSlim._(
          confidence: BuiltValueNullFieldError.checkNotNull(
              confidence, r'RecognitionResponseSlim', 'confidence'),
          createdAt: BuiltValueNullFieldError.checkNotNull(
              createdAt, r'RecognitionResponseSlim', 'createdAt'),
          id: BuiltValueNullFieldError.checkNotNull(
              id, r'RecognitionResponseSlim', 'id'),
          text: BuiltValueNullFieldError.checkNotNull(
              text, r'RecognitionResponseSlim', 'text'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

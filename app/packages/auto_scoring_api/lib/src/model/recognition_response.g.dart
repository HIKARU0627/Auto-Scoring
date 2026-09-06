// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'recognition_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$RecognitionResponse extends RecognitionResponse {
  @override
  final BuiltList<BoundingBoxResponse> boxes;
  @override
  final num confidence;
  @override
  final DateTime createdAt;
  @override
  final String id;
  @override
  final String questionId;
  @override
  final String source_;
  @override
  final String stage;
  @override
  final String submissionId;
  @override
  final String text;

  factory _$RecognitionResponse(
          [void Function(RecognitionResponseBuilder)? updates]) =>
      (RecognitionResponseBuilder()..update(updates))._build();

  _$RecognitionResponse._(
      {required this.boxes,
      required this.confidence,
      required this.createdAt,
      required this.id,
      required this.questionId,
      required this.source_,
      required this.stage,
      required this.submissionId,
      required this.text})
      : super._();
  @override
  RecognitionResponse rebuild(
          void Function(RecognitionResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  RecognitionResponseBuilder toBuilder() =>
      RecognitionResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is RecognitionResponse &&
        boxes == other.boxes &&
        confidence == other.confidence &&
        createdAt == other.createdAt &&
        id == other.id &&
        questionId == other.questionId &&
        source_ == other.source_ &&
        stage == other.stage &&
        submissionId == other.submissionId &&
        text == other.text;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, boxes.hashCode);
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, questionId.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, stage.hashCode);
    _$hash = $jc(_$hash, submissionId.hashCode);
    _$hash = $jc(_$hash, text.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'RecognitionResponse')
          ..add('boxes', boxes)
          ..add('confidence', confidence)
          ..add('createdAt', createdAt)
          ..add('id', id)
          ..add('questionId', questionId)
          ..add('source_', source_)
          ..add('stage', stage)
          ..add('submissionId', submissionId)
          ..add('text', text))
        .toString();
  }
}

class RecognitionResponseBuilder
    implements Builder<RecognitionResponse, RecognitionResponseBuilder> {
  _$RecognitionResponse? _$v;

  ListBuilder<BoundingBoxResponse>? _boxes;
  ListBuilder<BoundingBoxResponse> get boxes =>
      _$this._boxes ??= ListBuilder<BoundingBoxResponse>();
  set boxes(ListBuilder<BoundingBoxResponse>? boxes) => _$this._boxes = boxes;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _questionId;
  String? get questionId => _$this._questionId;
  set questionId(String? questionId) => _$this._questionId = questionId;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  String? _stage;
  String? get stage => _$this._stage;
  set stage(String? stage) => _$this._stage = stage;

  String? _submissionId;
  String? get submissionId => _$this._submissionId;
  set submissionId(String? submissionId) => _$this._submissionId = submissionId;

  String? _text;
  String? get text => _$this._text;
  set text(String? text) => _$this._text = text;

  RecognitionResponseBuilder() {
    RecognitionResponse._defaults(this);
  }

  RecognitionResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _boxes = $v.boxes.toBuilder();
      _confidence = $v.confidence;
      _createdAt = $v.createdAt;
      _id = $v.id;
      _questionId = $v.questionId;
      _source_ = $v.source_;
      _stage = $v.stage;
      _submissionId = $v.submissionId;
      _text = $v.text;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(RecognitionResponse other) {
    _$v = other as _$RecognitionResponse;
  }

  @override
  void update(void Function(RecognitionResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  RecognitionResponse build() => _build();

  _$RecognitionResponse _build() {
    _$RecognitionResponse _$result;
    try {
      _$result = _$v ??
          _$RecognitionResponse._(
            boxes: boxes.build(),
            confidence: BuiltValueNullFieldError.checkNotNull(
                confidence, r'RecognitionResponse', 'confidence'),
            createdAt: BuiltValueNullFieldError.checkNotNull(
                createdAt, r'RecognitionResponse', 'createdAt'),
            id: BuiltValueNullFieldError.checkNotNull(
                id, r'RecognitionResponse', 'id'),
            questionId: BuiltValueNullFieldError.checkNotNull(
                questionId, r'RecognitionResponse', 'questionId'),
            source_: BuiltValueNullFieldError.checkNotNull(
                source_, r'RecognitionResponse', 'source_'),
            stage: BuiltValueNullFieldError.checkNotNull(
                stage, r'RecognitionResponse', 'stage'),
            submissionId: BuiltValueNullFieldError.checkNotNull(
                submissionId, r'RecognitionResponse', 'submissionId'),
            text: BuiltValueNullFieldError.checkNotNull(
                text, r'RecognitionResponse', 'text'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'boxes';
        boxes.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'RecognitionResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

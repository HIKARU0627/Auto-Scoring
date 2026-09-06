// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'annotation_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$AnnotationResponse extends AnnotationResponse {
  @override
  final String? anchorText;
  @override
  final String? comment;
  @override
  final DateTime createdAt;
  @override
  final String id;
  @override
  final String kind;
  @override
  final String questionId;
  @override
  final NormalizedRectResponse? rect;
  @override
  final String source_;
  @override
  final String submissionId;

  factory _$AnnotationResponse(
          [void Function(AnnotationResponseBuilder)? updates]) =>
      (AnnotationResponseBuilder()..update(updates))._build();

  _$AnnotationResponse._(
      {this.anchorText,
      this.comment,
      required this.createdAt,
      required this.id,
      required this.kind,
      required this.questionId,
      this.rect,
      required this.source_,
      required this.submissionId})
      : super._();
  @override
  AnnotationResponse rebuild(
          void Function(AnnotationResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  AnnotationResponseBuilder toBuilder() =>
      AnnotationResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is AnnotationResponse &&
        anchorText == other.anchorText &&
        comment == other.comment &&
        createdAt == other.createdAt &&
        id == other.id &&
        kind == other.kind &&
        questionId == other.questionId &&
        rect == other.rect &&
        source_ == other.source_ &&
        submissionId == other.submissionId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, anchorText.hashCode);
    _$hash = $jc(_$hash, comment.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, kind.hashCode);
    _$hash = $jc(_$hash, questionId.hashCode);
    _$hash = $jc(_$hash, rect.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, submissionId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'AnnotationResponse')
          ..add('anchorText', anchorText)
          ..add('comment', comment)
          ..add('createdAt', createdAt)
          ..add('id', id)
          ..add('kind', kind)
          ..add('questionId', questionId)
          ..add('rect', rect)
          ..add('source_', source_)
          ..add('submissionId', submissionId))
        .toString();
  }
}

class AnnotationResponseBuilder
    implements Builder<AnnotationResponse, AnnotationResponseBuilder> {
  _$AnnotationResponse? _$v;

  String? _anchorText;
  String? get anchorText => _$this._anchorText;
  set anchorText(String? anchorText) => _$this._anchorText = anchorText;

  String? _comment;
  String? get comment => _$this._comment;
  set comment(String? comment) => _$this._comment = comment;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _kind;
  String? get kind => _$this._kind;
  set kind(String? kind) => _$this._kind = kind;

  String? _questionId;
  String? get questionId => _$this._questionId;
  set questionId(String? questionId) => _$this._questionId = questionId;

  NormalizedRectResponseBuilder? _rect;
  NormalizedRectResponseBuilder get rect =>
      _$this._rect ??= NormalizedRectResponseBuilder();
  set rect(NormalizedRectResponseBuilder? rect) => _$this._rect = rect;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  String? _submissionId;
  String? get submissionId => _$this._submissionId;
  set submissionId(String? submissionId) => _$this._submissionId = submissionId;

  AnnotationResponseBuilder() {
    AnnotationResponse._defaults(this);
  }

  AnnotationResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _anchorText = $v.anchorText;
      _comment = $v.comment;
      _createdAt = $v.createdAt;
      _id = $v.id;
      _kind = $v.kind;
      _questionId = $v.questionId;
      _rect = $v.rect?.toBuilder();
      _source_ = $v.source_;
      _submissionId = $v.submissionId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(AnnotationResponse other) {
    _$v = other as _$AnnotationResponse;
  }

  @override
  void update(void Function(AnnotationResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  AnnotationResponse build() => _build();

  _$AnnotationResponse _build() {
    _$AnnotationResponse _$result;
    try {
      _$result = _$v ??
          _$AnnotationResponse._(
            anchorText: anchorText,
            comment: comment,
            createdAt: BuiltValueNullFieldError.checkNotNull(
                createdAt, r'AnnotationResponse', 'createdAt'),
            id: BuiltValueNullFieldError.checkNotNull(
                id, r'AnnotationResponse', 'id'),
            kind: BuiltValueNullFieldError.checkNotNull(
                kind, r'AnnotationResponse', 'kind'),
            questionId: BuiltValueNullFieldError.checkNotNull(
                questionId, r'AnnotationResponse', 'questionId'),
            rect: _rect?.build(),
            source_: BuiltValueNullFieldError.checkNotNull(
                source_, r'AnnotationResponse', 'source_'),
            submissionId: BuiltValueNullFieldError.checkNotNull(
                submissionId, r'AnnotationResponse', 'submissionId'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'rect';
        _rect?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'AnnotationResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'review_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ReviewResponse extends ReviewResponse {
  @override
  final String action;
  @override
  final String? aiGradeResultId;
  @override
  final DateTime createdAt;
  @override
  final String? humanGradeResultId;
  @override
  final String id;
  @override
  final String? note;
  @override
  final String questionId;
  @override
  final String? regradeJobId;
  @override
  final String submissionId;
  @override
  final String? undoneReviewId;
  @override
  final int version;

  factory _$ReviewResponse([void Function(ReviewResponseBuilder)? updates]) =>
      (ReviewResponseBuilder()..update(updates))._build();

  _$ReviewResponse._(
      {required this.action,
      this.aiGradeResultId,
      required this.createdAt,
      this.humanGradeResultId,
      required this.id,
      this.note,
      required this.questionId,
      this.regradeJobId,
      required this.submissionId,
      this.undoneReviewId,
      required this.version})
      : super._();
  @override
  ReviewResponse rebuild(void Function(ReviewResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ReviewResponseBuilder toBuilder() => ReviewResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ReviewResponse &&
        action == other.action &&
        aiGradeResultId == other.aiGradeResultId &&
        createdAt == other.createdAt &&
        humanGradeResultId == other.humanGradeResultId &&
        id == other.id &&
        note == other.note &&
        questionId == other.questionId &&
        regradeJobId == other.regradeJobId &&
        submissionId == other.submissionId &&
        undoneReviewId == other.undoneReviewId &&
        version == other.version;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, action.hashCode);
    _$hash = $jc(_$hash, aiGradeResultId.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, humanGradeResultId.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, note.hashCode);
    _$hash = $jc(_$hash, questionId.hashCode);
    _$hash = $jc(_$hash, regradeJobId.hashCode);
    _$hash = $jc(_$hash, submissionId.hashCode);
    _$hash = $jc(_$hash, undoneReviewId.hashCode);
    _$hash = $jc(_$hash, version.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ReviewResponse')
          ..add('action', action)
          ..add('aiGradeResultId', aiGradeResultId)
          ..add('createdAt', createdAt)
          ..add('humanGradeResultId', humanGradeResultId)
          ..add('id', id)
          ..add('note', note)
          ..add('questionId', questionId)
          ..add('regradeJobId', regradeJobId)
          ..add('submissionId', submissionId)
          ..add('undoneReviewId', undoneReviewId)
          ..add('version', version))
        .toString();
  }
}

class ReviewResponseBuilder
    implements Builder<ReviewResponse, ReviewResponseBuilder> {
  _$ReviewResponse? _$v;

  String? _action;
  String? get action => _$this._action;
  set action(String? action) => _$this._action = action;

  String? _aiGradeResultId;
  String? get aiGradeResultId => _$this._aiGradeResultId;
  set aiGradeResultId(String? aiGradeResultId) =>
      _$this._aiGradeResultId = aiGradeResultId;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  String? _humanGradeResultId;
  String? get humanGradeResultId => _$this._humanGradeResultId;
  set humanGradeResultId(String? humanGradeResultId) =>
      _$this._humanGradeResultId = humanGradeResultId;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _note;
  String? get note => _$this._note;
  set note(String? note) => _$this._note = note;

  String? _questionId;
  String? get questionId => _$this._questionId;
  set questionId(String? questionId) => _$this._questionId = questionId;

  String? _regradeJobId;
  String? get regradeJobId => _$this._regradeJobId;
  set regradeJobId(String? regradeJobId) => _$this._regradeJobId = regradeJobId;

  String? _submissionId;
  String? get submissionId => _$this._submissionId;
  set submissionId(String? submissionId) => _$this._submissionId = submissionId;

  String? _undoneReviewId;
  String? get undoneReviewId => _$this._undoneReviewId;
  set undoneReviewId(String? undoneReviewId) =>
      _$this._undoneReviewId = undoneReviewId;

  int? _version;
  int? get version => _$this._version;
  set version(int? version) => _$this._version = version;

  ReviewResponseBuilder() {
    ReviewResponse._defaults(this);
  }

  ReviewResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _action = $v.action;
      _aiGradeResultId = $v.aiGradeResultId;
      _createdAt = $v.createdAt;
      _humanGradeResultId = $v.humanGradeResultId;
      _id = $v.id;
      _note = $v.note;
      _questionId = $v.questionId;
      _regradeJobId = $v.regradeJobId;
      _submissionId = $v.submissionId;
      _undoneReviewId = $v.undoneReviewId;
      _version = $v.version;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ReviewResponse other) {
    _$v = other as _$ReviewResponse;
  }

  @override
  void update(void Function(ReviewResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ReviewResponse build() => _build();

  _$ReviewResponse _build() {
    final _$result = _$v ??
        _$ReviewResponse._(
          action: BuiltValueNullFieldError.checkNotNull(
              action, r'ReviewResponse', 'action'),
          aiGradeResultId: aiGradeResultId,
          createdAt: BuiltValueNullFieldError.checkNotNull(
              createdAt, r'ReviewResponse', 'createdAt'),
          humanGradeResultId: humanGradeResultId,
          id: BuiltValueNullFieldError.checkNotNull(
              id, r'ReviewResponse', 'id'),
          note: note,
          questionId: BuiltValueNullFieldError.checkNotNull(
              questionId, r'ReviewResponse', 'questionId'),
          regradeJobId: regradeJobId,
          submissionId: BuiltValueNullFieldError.checkNotNull(
              submissionId, r'ReviewResponse', 'submissionId'),
          undoneReviewId: undoneReviewId,
          version: BuiltValueNullFieldError.checkNotNull(
              version, r'ReviewResponse', 'version'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

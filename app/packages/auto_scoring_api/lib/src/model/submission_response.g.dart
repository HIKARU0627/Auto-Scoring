// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'submission_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$SubmissionResponse extends SubmissionResponse {
  @override
  final DateTime createdAt;
  @override
  final String id;
  @override
  final bool? isRetry;
  @override
  final String? originalFilename;
  @override
  final int pageCount;
  @override
  final String? reviewReason;
  @override
  final String state;
  @override
  final String? studentLabel;
  @override
  final String testId;

  factory _$SubmissionResponse(
          [void Function(SubmissionResponseBuilder)? updates]) =>
      (SubmissionResponseBuilder()..update(updates))._build();

  _$SubmissionResponse._(
      {required this.createdAt,
      required this.id,
      this.isRetry,
      this.originalFilename,
      required this.pageCount,
      this.reviewReason,
      required this.state,
      this.studentLabel,
      required this.testId})
      : super._();
  @override
  SubmissionResponse rebuild(
          void Function(SubmissionResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  SubmissionResponseBuilder toBuilder() =>
      SubmissionResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is SubmissionResponse &&
        createdAt == other.createdAt &&
        id == other.id &&
        isRetry == other.isRetry &&
        originalFilename == other.originalFilename &&
        pageCount == other.pageCount &&
        reviewReason == other.reviewReason &&
        state == other.state &&
        studentLabel == other.studentLabel &&
        testId == other.testId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, isRetry.hashCode);
    _$hash = $jc(_$hash, originalFilename.hashCode);
    _$hash = $jc(_$hash, pageCount.hashCode);
    _$hash = $jc(_$hash, reviewReason.hashCode);
    _$hash = $jc(_$hash, state.hashCode);
    _$hash = $jc(_$hash, studentLabel.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'SubmissionResponse')
          ..add('createdAt', createdAt)
          ..add('id', id)
          ..add('isRetry', isRetry)
          ..add('originalFilename', originalFilename)
          ..add('pageCount', pageCount)
          ..add('reviewReason', reviewReason)
          ..add('state', state)
          ..add('studentLabel', studentLabel)
          ..add('testId', testId))
        .toString();
  }
}

class SubmissionResponseBuilder
    implements Builder<SubmissionResponse, SubmissionResponseBuilder> {
  _$SubmissionResponse? _$v;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  bool? _isRetry;
  bool? get isRetry => _$this._isRetry;
  set isRetry(bool? isRetry) => _$this._isRetry = isRetry;

  String? _originalFilename;
  String? get originalFilename => _$this._originalFilename;
  set originalFilename(String? originalFilename) =>
      _$this._originalFilename = originalFilename;

  int? _pageCount;
  int? get pageCount => _$this._pageCount;
  set pageCount(int? pageCount) => _$this._pageCount = pageCount;

  String? _reviewReason;
  String? get reviewReason => _$this._reviewReason;
  set reviewReason(String? reviewReason) => _$this._reviewReason = reviewReason;

  String? _state;
  String? get state => _$this._state;
  set state(String? state) => _$this._state = state;

  String? _studentLabel;
  String? get studentLabel => _$this._studentLabel;
  set studentLabel(String? studentLabel) => _$this._studentLabel = studentLabel;

  String? _testId;
  String? get testId => _$this._testId;
  set testId(String? testId) => _$this._testId = testId;

  SubmissionResponseBuilder() {
    SubmissionResponse._defaults(this);
  }

  SubmissionResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _createdAt = $v.createdAt;
      _id = $v.id;
      _isRetry = $v.isRetry;
      _originalFilename = $v.originalFilename;
      _pageCount = $v.pageCount;
      _reviewReason = $v.reviewReason;
      _state = $v.state;
      _studentLabel = $v.studentLabel;
      _testId = $v.testId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(SubmissionResponse other) {
    _$v = other as _$SubmissionResponse;
  }

  @override
  void update(void Function(SubmissionResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  SubmissionResponse build() => _build();

  _$SubmissionResponse _build() {
    final _$result = _$v ??
        _$SubmissionResponse._(
          createdAt: BuiltValueNullFieldError.checkNotNull(
              createdAt, r'SubmissionResponse', 'createdAt'),
          id: BuiltValueNullFieldError.checkNotNull(
              id, r'SubmissionResponse', 'id'),
          isRetry: isRetry,
          originalFilename: originalFilename,
          pageCount: BuiltValueNullFieldError.checkNotNull(
              pageCount, r'SubmissionResponse', 'pageCount'),
          reviewReason: reviewReason,
          state: BuiltValueNullFieldError.checkNotNull(
              state, r'SubmissionResponse', 'state'),
          studentLabel: studentLabel,
          testId: BuiltValueNullFieldError.checkNotNull(
              testId, r'SubmissionResponse', 'testId'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

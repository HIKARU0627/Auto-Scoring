// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'job_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$JobResponse extends JobResponse {
  @override
  final int attempts;
  @override
  final String? blockedOnQuestionId;
  @override
  final DateTime createdAt;
  @override
  final int? dependencyGraphVersion;
  @override
  final String? errorCode;
  @override
  final String id;
  @override
  final String kind;
  @override
  final String? lastError;
  @override
  final int maxAttempts;
  @override
  final String? questionId;
  @override
  final String state;
  @override
  final String submissionId;
  @override
  final DateTime updatedAt;
  @override
  final bool? usable;

  factory _$JobResponse([void Function(JobResponseBuilder)? updates]) =>
      (JobResponseBuilder()..update(updates))._build();

  _$JobResponse._(
      {required this.attempts,
      this.blockedOnQuestionId,
      required this.createdAt,
      this.dependencyGraphVersion,
      this.errorCode,
      required this.id,
      required this.kind,
      this.lastError,
      required this.maxAttempts,
      this.questionId,
      required this.state,
      required this.submissionId,
      required this.updatedAt,
      this.usable})
      : super._();
  @override
  JobResponse rebuild(void Function(JobResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  JobResponseBuilder toBuilder() => JobResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is JobResponse &&
        attempts == other.attempts &&
        blockedOnQuestionId == other.blockedOnQuestionId &&
        createdAt == other.createdAt &&
        dependencyGraphVersion == other.dependencyGraphVersion &&
        errorCode == other.errorCode &&
        id == other.id &&
        kind == other.kind &&
        lastError == other.lastError &&
        maxAttempts == other.maxAttempts &&
        questionId == other.questionId &&
        state == other.state &&
        submissionId == other.submissionId &&
        updatedAt == other.updatedAt &&
        usable == other.usable;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, attempts.hashCode);
    _$hash = $jc(_$hash, blockedOnQuestionId.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, dependencyGraphVersion.hashCode);
    _$hash = $jc(_$hash, errorCode.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, kind.hashCode);
    _$hash = $jc(_$hash, lastError.hashCode);
    _$hash = $jc(_$hash, maxAttempts.hashCode);
    _$hash = $jc(_$hash, questionId.hashCode);
    _$hash = $jc(_$hash, state.hashCode);
    _$hash = $jc(_$hash, submissionId.hashCode);
    _$hash = $jc(_$hash, updatedAt.hashCode);
    _$hash = $jc(_$hash, usable.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'JobResponse')
          ..add('attempts', attempts)
          ..add('blockedOnQuestionId', blockedOnQuestionId)
          ..add('createdAt', createdAt)
          ..add('dependencyGraphVersion', dependencyGraphVersion)
          ..add('errorCode', errorCode)
          ..add('id', id)
          ..add('kind', kind)
          ..add('lastError', lastError)
          ..add('maxAttempts', maxAttempts)
          ..add('questionId', questionId)
          ..add('state', state)
          ..add('submissionId', submissionId)
          ..add('updatedAt', updatedAt)
          ..add('usable', usable))
        .toString();
  }
}

class JobResponseBuilder implements Builder<JobResponse, JobResponseBuilder> {
  _$JobResponse? _$v;

  int? _attempts;
  int? get attempts => _$this._attempts;
  set attempts(int? attempts) => _$this._attempts = attempts;

  String? _blockedOnQuestionId;
  String? get blockedOnQuestionId => _$this._blockedOnQuestionId;
  set blockedOnQuestionId(String? blockedOnQuestionId) =>
      _$this._blockedOnQuestionId = blockedOnQuestionId;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  int? _dependencyGraphVersion;
  int? get dependencyGraphVersion => _$this._dependencyGraphVersion;
  set dependencyGraphVersion(int? dependencyGraphVersion) =>
      _$this._dependencyGraphVersion = dependencyGraphVersion;

  String? _errorCode;
  String? get errorCode => _$this._errorCode;
  set errorCode(String? errorCode) => _$this._errorCode = errorCode;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _kind;
  String? get kind => _$this._kind;
  set kind(String? kind) => _$this._kind = kind;

  String? _lastError;
  String? get lastError => _$this._lastError;
  set lastError(String? lastError) => _$this._lastError = lastError;

  int? _maxAttempts;
  int? get maxAttempts => _$this._maxAttempts;
  set maxAttempts(int? maxAttempts) => _$this._maxAttempts = maxAttempts;

  String? _questionId;
  String? get questionId => _$this._questionId;
  set questionId(String? questionId) => _$this._questionId = questionId;

  String? _state;
  String? get state => _$this._state;
  set state(String? state) => _$this._state = state;

  String? _submissionId;
  String? get submissionId => _$this._submissionId;
  set submissionId(String? submissionId) => _$this._submissionId = submissionId;

  DateTime? _updatedAt;
  DateTime? get updatedAt => _$this._updatedAt;
  set updatedAt(DateTime? updatedAt) => _$this._updatedAt = updatedAt;

  bool? _usable;
  bool? get usable => _$this._usable;
  set usable(bool? usable) => _$this._usable = usable;

  JobResponseBuilder() {
    JobResponse._defaults(this);
  }

  JobResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _attempts = $v.attempts;
      _blockedOnQuestionId = $v.blockedOnQuestionId;
      _createdAt = $v.createdAt;
      _dependencyGraphVersion = $v.dependencyGraphVersion;
      _errorCode = $v.errorCode;
      _id = $v.id;
      _kind = $v.kind;
      _lastError = $v.lastError;
      _maxAttempts = $v.maxAttempts;
      _questionId = $v.questionId;
      _state = $v.state;
      _submissionId = $v.submissionId;
      _updatedAt = $v.updatedAt;
      _usable = $v.usable;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(JobResponse other) {
    _$v = other as _$JobResponse;
  }

  @override
  void update(void Function(JobResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  JobResponse build() => _build();

  _$JobResponse _build() {
    final _$result = _$v ??
        _$JobResponse._(
          attempts: BuiltValueNullFieldError.checkNotNull(
              attempts, r'JobResponse', 'attempts'),
          blockedOnQuestionId: blockedOnQuestionId,
          createdAt: BuiltValueNullFieldError.checkNotNull(
              createdAt, r'JobResponse', 'createdAt'),
          dependencyGraphVersion: dependencyGraphVersion,
          errorCode: errorCode,
          id: BuiltValueNullFieldError.checkNotNull(id, r'JobResponse', 'id'),
          kind: BuiltValueNullFieldError.checkNotNull(
              kind, r'JobResponse', 'kind'),
          lastError: lastError,
          maxAttempts: BuiltValueNullFieldError.checkNotNull(
              maxAttempts, r'JobResponse', 'maxAttempts'),
          questionId: questionId,
          state: BuiltValueNullFieldError.checkNotNull(
              state, r'JobResponse', 'state'),
          submissionId: BuiltValueNullFieldError.checkNotNull(
              submissionId, r'JobResponse', 'submissionId'),
          updatedAt: BuiltValueNullFieldError.checkNotNull(
              updatedAt, r'JobResponse', 'updatedAt'),
          usable: usable,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'dependency_graph_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$DependencyGraphResponse extends DependencyGraphResponse {
  @override
  final DateTime? confirmedAt;
  @override
  final DateTime createdAt;
  @override
  final BuiltList<DependencyEdgeModel> edges;
  @override
  final String id;
  @override
  final BuiltList<BuiltList<String>> layers;
  @override
  final BuiltList<String> questionIds;
  @override
  final String status;
  @override
  final String testId;
  @override
  final BuiltList<UnresolvedQuestionModel> unresolved;
  @override
  final int version;

  factory _$DependencyGraphResponse(
          [void Function(DependencyGraphResponseBuilder)? updates]) =>
      (DependencyGraphResponseBuilder()..update(updates))._build();

  _$DependencyGraphResponse._(
      {this.confirmedAt,
      required this.createdAt,
      required this.edges,
      required this.id,
      required this.layers,
      required this.questionIds,
      required this.status,
      required this.testId,
      required this.unresolved,
      required this.version})
      : super._();
  @override
  DependencyGraphResponse rebuild(
          void Function(DependencyGraphResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  DependencyGraphResponseBuilder toBuilder() =>
      DependencyGraphResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is DependencyGraphResponse &&
        confirmedAt == other.confirmedAt &&
        createdAt == other.createdAt &&
        edges == other.edges &&
        id == other.id &&
        layers == other.layers &&
        questionIds == other.questionIds &&
        status == other.status &&
        testId == other.testId &&
        unresolved == other.unresolved &&
        version == other.version;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, confirmedAt.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, edges.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, layers.hashCode);
    _$hash = $jc(_$hash, questionIds.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jc(_$hash, unresolved.hashCode);
    _$hash = $jc(_$hash, version.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'DependencyGraphResponse')
          ..add('confirmedAt', confirmedAt)
          ..add('createdAt', createdAt)
          ..add('edges', edges)
          ..add('id', id)
          ..add('layers', layers)
          ..add('questionIds', questionIds)
          ..add('status', status)
          ..add('testId', testId)
          ..add('unresolved', unresolved)
          ..add('version', version))
        .toString();
  }
}

class DependencyGraphResponseBuilder
    implements
        Builder<DependencyGraphResponse, DependencyGraphResponseBuilder> {
  _$DependencyGraphResponse? _$v;

  DateTime? _confirmedAt;
  DateTime? get confirmedAt => _$this._confirmedAt;
  set confirmedAt(DateTime? confirmedAt) => _$this._confirmedAt = confirmedAt;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  ListBuilder<DependencyEdgeModel>? _edges;
  ListBuilder<DependencyEdgeModel> get edges =>
      _$this._edges ??= ListBuilder<DependencyEdgeModel>();
  set edges(ListBuilder<DependencyEdgeModel>? edges) => _$this._edges = edges;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  ListBuilder<BuiltList<String>>? _layers;
  ListBuilder<BuiltList<String>> get layers =>
      _$this._layers ??= ListBuilder<BuiltList<String>>();
  set layers(ListBuilder<BuiltList<String>>? layers) => _$this._layers = layers;

  ListBuilder<String>? _questionIds;
  ListBuilder<String> get questionIds =>
      _$this._questionIds ??= ListBuilder<String>();
  set questionIds(ListBuilder<String>? questionIds) =>
      _$this._questionIds = questionIds;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  String? _testId;
  String? get testId => _$this._testId;
  set testId(String? testId) => _$this._testId = testId;

  ListBuilder<UnresolvedQuestionModel>? _unresolved;
  ListBuilder<UnresolvedQuestionModel> get unresolved =>
      _$this._unresolved ??= ListBuilder<UnresolvedQuestionModel>();
  set unresolved(ListBuilder<UnresolvedQuestionModel>? unresolved) =>
      _$this._unresolved = unresolved;

  int? _version;
  int? get version => _$this._version;
  set version(int? version) => _$this._version = version;

  DependencyGraphResponseBuilder() {
    DependencyGraphResponse._defaults(this);
  }

  DependencyGraphResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _confirmedAt = $v.confirmedAt;
      _createdAt = $v.createdAt;
      _edges = $v.edges.toBuilder();
      _id = $v.id;
      _layers = $v.layers.toBuilder();
      _questionIds = $v.questionIds.toBuilder();
      _status = $v.status;
      _testId = $v.testId;
      _unresolved = $v.unresolved.toBuilder();
      _version = $v.version;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(DependencyGraphResponse other) {
    _$v = other as _$DependencyGraphResponse;
  }

  @override
  void update(void Function(DependencyGraphResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  DependencyGraphResponse build() => _build();

  _$DependencyGraphResponse _build() {
    _$DependencyGraphResponse _$result;
    try {
      _$result = _$v ??
          _$DependencyGraphResponse._(
            confirmedAt: confirmedAt,
            createdAt: BuiltValueNullFieldError.checkNotNull(
                createdAt, r'DependencyGraphResponse', 'createdAt'),
            edges: edges.build(),
            id: BuiltValueNullFieldError.checkNotNull(
                id, r'DependencyGraphResponse', 'id'),
            layers: layers.build(),
            questionIds: questionIds.build(),
            status: BuiltValueNullFieldError.checkNotNull(
                status, r'DependencyGraphResponse', 'status'),
            testId: BuiltValueNullFieldError.checkNotNull(
                testId, r'DependencyGraphResponse', 'testId'),
            unresolved: unresolved.build(),
            version: BuiltValueNullFieldError.checkNotNull(
                version, r'DependencyGraphResponse', 'version'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'edges';
        edges.build();

        _$failedField = 'layers';
        layers.build();
        _$failedField = 'questionIds';
        questionIds.build();

        _$failedField = 'unresolved';
        unresolved.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'DependencyGraphResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

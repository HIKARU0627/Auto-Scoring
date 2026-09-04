// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'dependency_edge_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$DependencyEdgeModel extends DependencyEdgeModel {
  @override
  final num? confidence;
  @override
  final String fromQuestionId;
  @override
  final BuiltList<String> provides;
  @override
  final String rationale;
  @override
  final String toQuestionId;

  factory _$DependencyEdgeModel(
          [void Function(DependencyEdgeModelBuilder)? updates]) =>
      (DependencyEdgeModelBuilder()..update(updates))._build();

  _$DependencyEdgeModel._(
      {this.confidence,
      required this.fromQuestionId,
      required this.provides,
      required this.rationale,
      required this.toQuestionId})
      : super._();
  @override
  DependencyEdgeModel rebuild(
          void Function(DependencyEdgeModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  DependencyEdgeModelBuilder toBuilder() =>
      DependencyEdgeModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is DependencyEdgeModel &&
        confidence == other.confidence &&
        fromQuestionId == other.fromQuestionId &&
        provides == other.provides &&
        rationale == other.rationale &&
        toQuestionId == other.toQuestionId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, fromQuestionId.hashCode);
    _$hash = $jc(_$hash, provides.hashCode);
    _$hash = $jc(_$hash, rationale.hashCode);
    _$hash = $jc(_$hash, toQuestionId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'DependencyEdgeModel')
          ..add('confidence', confidence)
          ..add('fromQuestionId', fromQuestionId)
          ..add('provides', provides)
          ..add('rationale', rationale)
          ..add('toQuestionId', toQuestionId))
        .toString();
  }
}

class DependencyEdgeModelBuilder
    implements Builder<DependencyEdgeModel, DependencyEdgeModelBuilder> {
  _$DependencyEdgeModel? _$v;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  String? _fromQuestionId;
  String? get fromQuestionId => _$this._fromQuestionId;
  set fromQuestionId(String? fromQuestionId) =>
      _$this._fromQuestionId = fromQuestionId;

  ListBuilder<String>? _provides;
  ListBuilder<String> get provides =>
      _$this._provides ??= ListBuilder<String>();
  set provides(ListBuilder<String>? provides) => _$this._provides = provides;

  String? _rationale;
  String? get rationale => _$this._rationale;
  set rationale(String? rationale) => _$this._rationale = rationale;

  String? _toQuestionId;
  String? get toQuestionId => _$this._toQuestionId;
  set toQuestionId(String? toQuestionId) => _$this._toQuestionId = toQuestionId;

  DependencyEdgeModelBuilder() {
    DependencyEdgeModel._defaults(this);
  }

  DependencyEdgeModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _confidence = $v.confidence;
      _fromQuestionId = $v.fromQuestionId;
      _provides = $v.provides.toBuilder();
      _rationale = $v.rationale;
      _toQuestionId = $v.toQuestionId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(DependencyEdgeModel other) {
    _$v = other as _$DependencyEdgeModel;
  }

  @override
  void update(void Function(DependencyEdgeModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  DependencyEdgeModel build() => _build();

  _$DependencyEdgeModel _build() {
    _$DependencyEdgeModel _$result;
    try {
      _$result = _$v ??
          _$DependencyEdgeModel._(
            confidence: confidence,
            fromQuestionId: BuiltValueNullFieldError.checkNotNull(
                fromQuestionId, r'DependencyEdgeModel', 'fromQuestionId'),
            provides: provides.build(),
            rationale: BuiltValueNullFieldError.checkNotNull(
                rationale, r'DependencyEdgeModel', 'rationale'),
            toQuestionId: BuiltValueNullFieldError.checkNotNull(
                toQuestionId, r'DependencyEdgeModel', 'toQuestionId'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'provides';
        provides.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'DependencyEdgeModel', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

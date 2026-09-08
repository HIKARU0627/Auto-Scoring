// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'classification_estimate_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ClassificationEstimateModel extends ClassificationEstimateModel {
  @override
  final int cached;
  @override
  final int notNeeded;
  @override
  final int pending;
  @override
  final int unsupported;

  factory _$ClassificationEstimateModel(
          [void Function(ClassificationEstimateModelBuilder)? updates]) =>
      (ClassificationEstimateModelBuilder()..update(updates))._build();

  _$ClassificationEstimateModel._(
      {required this.cached,
      required this.notNeeded,
      required this.pending,
      required this.unsupported})
      : super._();
  @override
  ClassificationEstimateModel rebuild(
          void Function(ClassificationEstimateModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ClassificationEstimateModelBuilder toBuilder() =>
      ClassificationEstimateModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ClassificationEstimateModel &&
        cached == other.cached &&
        notNeeded == other.notNeeded &&
        pending == other.pending &&
        unsupported == other.unsupported;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, cached.hashCode);
    _$hash = $jc(_$hash, notNeeded.hashCode);
    _$hash = $jc(_$hash, pending.hashCode);
    _$hash = $jc(_$hash, unsupported.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ClassificationEstimateModel')
          ..add('cached', cached)
          ..add('notNeeded', notNeeded)
          ..add('pending', pending)
          ..add('unsupported', unsupported))
        .toString();
  }
}

class ClassificationEstimateModelBuilder
    implements
        Builder<ClassificationEstimateModel,
            ClassificationEstimateModelBuilder> {
  _$ClassificationEstimateModel? _$v;

  int? _cached;
  int? get cached => _$this._cached;
  set cached(int? cached) => _$this._cached = cached;

  int? _notNeeded;
  int? get notNeeded => _$this._notNeeded;
  set notNeeded(int? notNeeded) => _$this._notNeeded = notNeeded;

  int? _pending;
  int? get pending => _$this._pending;
  set pending(int? pending) => _$this._pending = pending;

  int? _unsupported;
  int? get unsupported => _$this._unsupported;
  set unsupported(int? unsupported) => _$this._unsupported = unsupported;

  ClassificationEstimateModelBuilder() {
    ClassificationEstimateModel._defaults(this);
  }

  ClassificationEstimateModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _cached = $v.cached;
      _notNeeded = $v.notNeeded;
      _pending = $v.pending;
      _unsupported = $v.unsupported;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ClassificationEstimateModel other) {
    _$v = other as _$ClassificationEstimateModel;
  }

  @override
  void update(void Function(ClassificationEstimateModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ClassificationEstimateModel build() => _build();

  _$ClassificationEstimateModel _build() {
    final _$result = _$v ??
        _$ClassificationEstimateModel._(
          cached: BuiltValueNullFieldError.checkNotNull(
              cached, r'ClassificationEstimateModel', 'cached'),
          notNeeded: BuiltValueNullFieldError.checkNotNull(
              notNeeded, r'ClassificationEstimateModel', 'notNeeded'),
          pending: BuiltValueNullFieldError.checkNotNull(
              pending, r'ClassificationEstimateModel', 'pending'),
          unsupported: BuiltValueNullFieldError.checkNotNull(
              unsupported, r'ClassificationEstimateModel', 'unsupported'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

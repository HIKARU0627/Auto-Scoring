// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'confirm_criteria_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ConfirmCriteriaRequest extends ConfirmCriteriaRequest {
  @override
  final int revision;

  factory _$ConfirmCriteriaRequest(
          [void Function(ConfirmCriteriaRequestBuilder)? updates]) =>
      (ConfirmCriteriaRequestBuilder()..update(updates))._build();

  _$ConfirmCriteriaRequest._({required this.revision}) : super._();
  @override
  ConfirmCriteriaRequest rebuild(
          void Function(ConfirmCriteriaRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ConfirmCriteriaRequestBuilder toBuilder() =>
      ConfirmCriteriaRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ConfirmCriteriaRequest && revision == other.revision;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, revision.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ConfirmCriteriaRequest')
          ..add('revision', revision))
        .toString();
  }
}

class ConfirmCriteriaRequestBuilder
    implements Builder<ConfirmCriteriaRequest, ConfirmCriteriaRequestBuilder> {
  _$ConfirmCriteriaRequest? _$v;

  int? _revision;
  int? get revision => _$this._revision;
  set revision(int? revision) => _$this._revision = revision;

  ConfirmCriteriaRequestBuilder() {
    ConfirmCriteriaRequest._defaults(this);
  }

  ConfirmCriteriaRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _revision = $v.revision;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ConfirmCriteriaRequest other) {
    _$v = other as _$ConfirmCriteriaRequest;
  }

  @override
  void update(void Function(ConfirmCriteriaRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ConfirmCriteriaRequest build() => _build();

  _$ConfirmCriteriaRequest _build() {
    final _$result = _$v ??
        _$ConfirmCriteriaRequest._(
          revision: BuiltValueNullFieldError.checkNotNull(
              revision, r'ConfirmCriteriaRequest', 'revision'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

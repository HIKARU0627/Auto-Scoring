// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'confirm_profile_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ConfirmProfileRequest extends ConfirmProfileRequest {
  @override
  final int revision;

  factory _$ConfirmProfileRequest(
          [void Function(ConfirmProfileRequestBuilder)? updates]) =>
      (ConfirmProfileRequestBuilder()..update(updates))._build();

  _$ConfirmProfileRequest._({required this.revision}) : super._();
  @override
  ConfirmProfileRequest rebuild(
          void Function(ConfirmProfileRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ConfirmProfileRequestBuilder toBuilder() =>
      ConfirmProfileRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ConfirmProfileRequest && revision == other.revision;
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
    return (newBuiltValueToStringHelper(r'ConfirmProfileRequest')
          ..add('revision', revision))
        .toString();
  }
}

class ConfirmProfileRequestBuilder
    implements Builder<ConfirmProfileRequest, ConfirmProfileRequestBuilder> {
  _$ConfirmProfileRequest? _$v;

  int? _revision;
  int? get revision => _$this._revision;
  set revision(int? revision) => _$this._revision = revision;

  ConfirmProfileRequestBuilder() {
    ConfirmProfileRequest._defaults(this);
  }

  ConfirmProfileRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _revision = $v.revision;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ConfirmProfileRequest other) {
    _$v = other as _$ConfirmProfileRequest;
  }

  @override
  void update(void Function(ConfirmProfileRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ConfirmProfileRequest build() => _build();

  _$ConfirmProfileRequest _build() {
    final _$result = _$v ??
        _$ConfirmProfileRequest._(
          revision: BuiltValueNullFieldError.checkNotNull(
              revision, r'ConfirmProfileRequest', 'revision'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

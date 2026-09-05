// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'update_profile_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$UpdateProfileRequest extends UpdateProfileRequest {
  @override
  final BuiltList<RegionModel>? regions;

  factory _$UpdateProfileRequest(
          [void Function(UpdateProfileRequestBuilder)? updates]) =>
      (UpdateProfileRequestBuilder()..update(updates))._build();

  _$UpdateProfileRequest._({this.regions}) : super._();
  @override
  UpdateProfileRequest rebuild(
          void Function(UpdateProfileRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  UpdateProfileRequestBuilder toBuilder() =>
      UpdateProfileRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is UpdateProfileRequest && regions == other.regions;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, regions.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'UpdateProfileRequest')
          ..add('regions', regions))
        .toString();
  }
}

class UpdateProfileRequestBuilder
    implements Builder<UpdateProfileRequest, UpdateProfileRequestBuilder> {
  _$UpdateProfileRequest? _$v;

  ListBuilder<RegionModel>? _regions;
  ListBuilder<RegionModel> get regions =>
      _$this._regions ??= ListBuilder<RegionModel>();
  set regions(ListBuilder<RegionModel>? regions) => _$this._regions = regions;

  UpdateProfileRequestBuilder() {
    UpdateProfileRequest._defaults(this);
  }

  UpdateProfileRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _regions = $v.regions?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(UpdateProfileRequest other) {
    _$v = other as _$UpdateProfileRequest;
  }

  @override
  void update(void Function(UpdateProfileRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  UpdateProfileRequest build() => _build();

  _$UpdateProfileRequest _build() {
    _$UpdateProfileRequest _$result;
    try {
      _$result = _$v ??
          _$UpdateProfileRequest._(
            regions: _regions?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'regions';
        _regions?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'UpdateProfileRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

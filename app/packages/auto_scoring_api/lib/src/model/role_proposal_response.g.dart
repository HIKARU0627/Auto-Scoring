// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'role_proposal_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$RoleProposalResponse extends RoleProposalResponse {
  @override
  final bool cached;
  @override
  final num confidence;
  @override
  final MaterialRole? role;

  factory _$RoleProposalResponse(
          [void Function(RoleProposalResponseBuilder)? updates]) =>
      (RoleProposalResponseBuilder()..update(updates))._build();

  _$RoleProposalResponse._(
      {required this.cached, required this.confidence, this.role})
      : super._();
  @override
  RoleProposalResponse rebuild(
          void Function(RoleProposalResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  RoleProposalResponseBuilder toBuilder() =>
      RoleProposalResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is RoleProposalResponse &&
        cached == other.cached &&
        confidence == other.confidence &&
        role == other.role;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, cached.hashCode);
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, role.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'RoleProposalResponse')
          ..add('cached', cached)
          ..add('confidence', confidence)
          ..add('role', role))
        .toString();
  }
}

class RoleProposalResponseBuilder
    implements Builder<RoleProposalResponse, RoleProposalResponseBuilder> {
  _$RoleProposalResponse? _$v;

  bool? _cached;
  bool? get cached => _$this._cached;
  set cached(bool? cached) => _$this._cached = cached;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  MaterialRole? _role;
  MaterialRole? get role => _$this._role;
  set role(MaterialRole? role) => _$this._role = role;

  RoleProposalResponseBuilder() {
    RoleProposalResponse._defaults(this);
  }

  RoleProposalResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _cached = $v.cached;
      _confidence = $v.confidence;
      _role = $v.role;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(RoleProposalResponse other) {
    _$v = other as _$RoleProposalResponse;
  }

  @override
  void update(void Function(RoleProposalResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  RoleProposalResponse build() => _build();

  _$RoleProposalResponse _build() {
    final _$result = _$v ??
        _$RoleProposalResponse._(
          cached: BuiltValueNullFieldError.checkNotNull(
              cached, r'RoleProposalResponse', 'cached'),
          confidence: BuiltValueNullFieldError.checkNotNull(
              confidence, r'RoleProposalResponse', 'confidence'),
          role: role,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

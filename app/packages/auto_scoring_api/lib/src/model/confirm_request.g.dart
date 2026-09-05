// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'confirm_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ConfirmRequest extends ConfirmRequest {
  @override
  final BuiltList<DependencyEdgeModel> edges;
  @override
  final int version;

  factory _$ConfirmRequest([void Function(ConfirmRequestBuilder)? updates]) =>
      (ConfirmRequestBuilder()..update(updates))._build();

  _$ConfirmRequest._({required this.edges, required this.version}) : super._();
  @override
  ConfirmRequest rebuild(void Function(ConfirmRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ConfirmRequestBuilder toBuilder() => ConfirmRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ConfirmRequest &&
        edges == other.edges &&
        version == other.version;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, edges.hashCode);
    _$hash = $jc(_$hash, version.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ConfirmRequest')
          ..add('edges', edges)
          ..add('version', version))
        .toString();
  }
}

class ConfirmRequestBuilder
    implements Builder<ConfirmRequest, ConfirmRequestBuilder> {
  _$ConfirmRequest? _$v;

  ListBuilder<DependencyEdgeModel>? _edges;
  ListBuilder<DependencyEdgeModel> get edges =>
      _$this._edges ??= ListBuilder<DependencyEdgeModel>();
  set edges(ListBuilder<DependencyEdgeModel>? edges) => _$this._edges = edges;

  int? _version;
  int? get version => _$this._version;
  set version(int? version) => _$this._version = version;

  ConfirmRequestBuilder() {
    ConfirmRequest._defaults(this);
  }

  ConfirmRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _edges = $v.edges.toBuilder();
      _version = $v.version;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ConfirmRequest other) {
    _$v = other as _$ConfirmRequest;
  }

  @override
  void update(void Function(ConfirmRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ConfirmRequest build() => _build();

  _$ConfirmRequest _build() {
    _$ConfirmRequest _$result;
    try {
      _$result = _$v ??
          _$ConfirmRequest._(
            edges: edges.build(),
            version: BuiltValueNullFieldError.checkNotNull(
                version, r'ConfirmRequest', 'version'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'edges';
        edges.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ConfirmRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

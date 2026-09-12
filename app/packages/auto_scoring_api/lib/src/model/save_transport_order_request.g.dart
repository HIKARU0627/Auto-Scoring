// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'save_transport_order_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$SaveTransportOrderRequest extends SaveTransportOrderRequest {
  @override
  final BuiltList<String> order;

  factory _$SaveTransportOrderRequest(
          [void Function(SaveTransportOrderRequestBuilder)? updates]) =>
      (SaveTransportOrderRequestBuilder()..update(updates))._build();

  _$SaveTransportOrderRequest._({required this.order}) : super._();
  @override
  SaveTransportOrderRequest rebuild(
          void Function(SaveTransportOrderRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  SaveTransportOrderRequestBuilder toBuilder() =>
      SaveTransportOrderRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is SaveTransportOrderRequest && order == other.order;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, order.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'SaveTransportOrderRequest')
          ..add('order', order))
        .toString();
  }
}

class SaveTransportOrderRequestBuilder
    implements
        Builder<SaveTransportOrderRequest, SaveTransportOrderRequestBuilder> {
  _$SaveTransportOrderRequest? _$v;

  ListBuilder<String>? _order;
  ListBuilder<String> get order => _$this._order ??= ListBuilder<String>();
  set order(ListBuilder<String>? order) => _$this._order = order;

  SaveTransportOrderRequestBuilder() {
    SaveTransportOrderRequest._defaults(this);
  }

  SaveTransportOrderRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _order = $v.order.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(SaveTransportOrderRequest other) {
    _$v = other as _$SaveTransportOrderRequest;
  }

  @override
  void update(void Function(SaveTransportOrderRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  SaveTransportOrderRequest build() => _build();

  _$SaveTransportOrderRequest _build() {
    _$SaveTransportOrderRequest _$result;
    try {
      _$result = _$v ??
          _$SaveTransportOrderRequest._(
            order: order.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'order';
        order.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'SaveTransportOrderRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

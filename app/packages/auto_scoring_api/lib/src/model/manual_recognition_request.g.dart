// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'manual_recognition_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ManualRecognitionRequest extends ManualRecognitionRequest {
  @override
  final String text;

  factory _$ManualRecognitionRequest(
          [void Function(ManualRecognitionRequestBuilder)? updates]) =>
      (ManualRecognitionRequestBuilder()..update(updates))._build();

  _$ManualRecognitionRequest._({required this.text}) : super._();
  @override
  ManualRecognitionRequest rebuild(
          void Function(ManualRecognitionRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ManualRecognitionRequestBuilder toBuilder() =>
      ManualRecognitionRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ManualRecognitionRequest && text == other.text;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, text.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ManualRecognitionRequest')
          ..add('text', text))
        .toString();
  }
}

class ManualRecognitionRequestBuilder
    implements
        Builder<ManualRecognitionRequest, ManualRecognitionRequestBuilder> {
  _$ManualRecognitionRequest? _$v;

  String? _text;
  String? get text => _$this._text;
  set text(String? text) => _$this._text = text;

  ManualRecognitionRequestBuilder() {
    ManualRecognitionRequest._defaults(this);
  }

  ManualRecognitionRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _text = $v.text;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ManualRecognitionRequest other) {
    _$v = other as _$ManualRecognitionRequest;
  }

  @override
  void update(void Function(ManualRecognitionRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ManualRecognitionRequest build() => _build();

  _$ManualRecognitionRequest _build() {
    final _$result = _$v ??
        _$ManualRecognitionRequest._(
          text: BuiltValueNullFieldError.checkNotNull(
              text, r'ManualRecognitionRequest', 'text'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'complete_registration_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CompleteRegistrationResponse extends CompleteRegistrationResponse {
  @override
  final bool dependencyGraphConfirmed;
  @override
  final bool profileConfirmed;
  @override
  final TestResponse test;

  factory _$CompleteRegistrationResponse(
          [void Function(CompleteRegistrationResponseBuilder)? updates]) =>
      (CompleteRegistrationResponseBuilder()..update(updates))._build();

  _$CompleteRegistrationResponse._(
      {required this.dependencyGraphConfirmed,
      required this.profileConfirmed,
      required this.test})
      : super._();
  @override
  CompleteRegistrationResponse rebuild(
          void Function(CompleteRegistrationResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CompleteRegistrationResponseBuilder toBuilder() =>
      CompleteRegistrationResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CompleteRegistrationResponse &&
        dependencyGraphConfirmed == other.dependencyGraphConfirmed &&
        profileConfirmed == other.profileConfirmed &&
        test == other.test;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, dependencyGraphConfirmed.hashCode);
    _$hash = $jc(_$hash, profileConfirmed.hashCode);
    _$hash = $jc(_$hash, test.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CompleteRegistrationResponse')
          ..add('dependencyGraphConfirmed', dependencyGraphConfirmed)
          ..add('profileConfirmed', profileConfirmed)
          ..add('test', test))
        .toString();
  }
}

class CompleteRegistrationResponseBuilder
    implements
        Builder<CompleteRegistrationResponse,
            CompleteRegistrationResponseBuilder> {
  _$CompleteRegistrationResponse? _$v;

  bool? _dependencyGraphConfirmed;
  bool? get dependencyGraphConfirmed => _$this._dependencyGraphConfirmed;
  set dependencyGraphConfirmed(bool? dependencyGraphConfirmed) =>
      _$this._dependencyGraphConfirmed = dependencyGraphConfirmed;

  bool? _profileConfirmed;
  bool? get profileConfirmed => _$this._profileConfirmed;
  set profileConfirmed(bool? profileConfirmed) =>
      _$this._profileConfirmed = profileConfirmed;

  TestResponseBuilder? _test;
  TestResponseBuilder get test => _$this._test ??= TestResponseBuilder();
  set test(TestResponseBuilder? test) => _$this._test = test;

  CompleteRegistrationResponseBuilder() {
    CompleteRegistrationResponse._defaults(this);
  }

  CompleteRegistrationResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _dependencyGraphConfirmed = $v.dependencyGraphConfirmed;
      _profileConfirmed = $v.profileConfirmed;
      _test = $v.test.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CompleteRegistrationResponse other) {
    _$v = other as _$CompleteRegistrationResponse;
  }

  @override
  void update(void Function(CompleteRegistrationResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CompleteRegistrationResponse build() => _build();

  _$CompleteRegistrationResponse _build() {
    _$CompleteRegistrationResponse _$result;
    try {
      _$result = _$v ??
          _$CompleteRegistrationResponse._(
            dependencyGraphConfirmed: BuiltValueNullFieldError.checkNotNull(
                dependencyGraphConfirmed,
                r'CompleteRegistrationResponse',
                'dependencyGraphConfirmed'),
            profileConfirmed: BuiltValueNullFieldError.checkNotNull(
                profileConfirmed,
                r'CompleteRegistrationResponse',
                'profileConfirmed'),
            test: test.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'test';
        test.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CompleteRegistrationResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'error_catalog_entry_input.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ErrorCatalogEntryInput extends ErrorCatalogEntryInput {
  @override
  final String? deduction;
  @override
  final String mistake;
  @override
  final String? questionLabel;
  @override
  final String redInk;
  @override
  final String? roundLabel;

  factory _$ErrorCatalogEntryInput(
          [void Function(ErrorCatalogEntryInputBuilder)? updates]) =>
      (ErrorCatalogEntryInputBuilder()..update(updates))._build();

  _$ErrorCatalogEntryInput._(
      {this.deduction,
      required this.mistake,
      this.questionLabel,
      required this.redInk,
      this.roundLabel})
      : super._();
  @override
  ErrorCatalogEntryInput rebuild(
          void Function(ErrorCatalogEntryInputBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ErrorCatalogEntryInputBuilder toBuilder() =>
      ErrorCatalogEntryInputBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ErrorCatalogEntryInput &&
        deduction == other.deduction &&
        mistake == other.mistake &&
        questionLabel == other.questionLabel &&
        redInk == other.redInk &&
        roundLabel == other.roundLabel;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, deduction.hashCode);
    _$hash = $jc(_$hash, mistake.hashCode);
    _$hash = $jc(_$hash, questionLabel.hashCode);
    _$hash = $jc(_$hash, redInk.hashCode);
    _$hash = $jc(_$hash, roundLabel.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ErrorCatalogEntryInput')
          ..add('deduction', deduction)
          ..add('mistake', mistake)
          ..add('questionLabel', questionLabel)
          ..add('redInk', redInk)
          ..add('roundLabel', roundLabel))
        .toString();
  }
}

class ErrorCatalogEntryInputBuilder
    implements Builder<ErrorCatalogEntryInput, ErrorCatalogEntryInputBuilder> {
  _$ErrorCatalogEntryInput? _$v;

  String? _deduction;
  String? get deduction => _$this._deduction;
  set deduction(String? deduction) => _$this._deduction = deduction;

  String? _mistake;
  String? get mistake => _$this._mistake;
  set mistake(String? mistake) => _$this._mistake = mistake;

  String? _questionLabel;
  String? get questionLabel => _$this._questionLabel;
  set questionLabel(String? questionLabel) =>
      _$this._questionLabel = questionLabel;

  String? _redInk;
  String? get redInk => _$this._redInk;
  set redInk(String? redInk) => _$this._redInk = redInk;

  String? _roundLabel;
  String? get roundLabel => _$this._roundLabel;
  set roundLabel(String? roundLabel) => _$this._roundLabel = roundLabel;

  ErrorCatalogEntryInputBuilder() {
    ErrorCatalogEntryInput._defaults(this);
  }

  ErrorCatalogEntryInputBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _deduction = $v.deduction;
      _mistake = $v.mistake;
      _questionLabel = $v.questionLabel;
      _redInk = $v.redInk;
      _roundLabel = $v.roundLabel;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ErrorCatalogEntryInput other) {
    _$v = other as _$ErrorCatalogEntryInput;
  }

  @override
  void update(void Function(ErrorCatalogEntryInputBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ErrorCatalogEntryInput build() => _build();

  _$ErrorCatalogEntryInput _build() {
    final _$result = _$v ??
        _$ErrorCatalogEntryInput._(
          deduction: deduction,
          mistake: BuiltValueNullFieldError.checkNotNull(
              mistake, r'ErrorCatalogEntryInput', 'mistake'),
          questionLabel: questionLabel,
          redInk: BuiltValueNullFieldError.checkNotNull(
              redInk, r'ErrorCatalogEntryInput', 'redInk'),
          roundLabel: roundLabel,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

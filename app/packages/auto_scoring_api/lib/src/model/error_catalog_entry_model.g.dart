// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'error_catalog_entry_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ErrorCatalogEntryModel extends ErrorCatalogEntryModel {
  @override
  final String? deduction;
  @override
  final bool? edited;
  @override
  final String mistake;
  @override
  final String? questionLabel;
  @override
  final String redInk;
  @override
  final String? roundLabel;

  factory _$ErrorCatalogEntryModel(
          [void Function(ErrorCatalogEntryModelBuilder)? updates]) =>
      (ErrorCatalogEntryModelBuilder()..update(updates))._build();

  _$ErrorCatalogEntryModel._(
      {this.deduction,
      this.edited,
      required this.mistake,
      this.questionLabel,
      required this.redInk,
      this.roundLabel})
      : super._();
  @override
  ErrorCatalogEntryModel rebuild(
          void Function(ErrorCatalogEntryModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ErrorCatalogEntryModelBuilder toBuilder() =>
      ErrorCatalogEntryModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ErrorCatalogEntryModel &&
        deduction == other.deduction &&
        edited == other.edited &&
        mistake == other.mistake &&
        questionLabel == other.questionLabel &&
        redInk == other.redInk &&
        roundLabel == other.roundLabel;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, deduction.hashCode);
    _$hash = $jc(_$hash, edited.hashCode);
    _$hash = $jc(_$hash, mistake.hashCode);
    _$hash = $jc(_$hash, questionLabel.hashCode);
    _$hash = $jc(_$hash, redInk.hashCode);
    _$hash = $jc(_$hash, roundLabel.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ErrorCatalogEntryModel')
          ..add('deduction', deduction)
          ..add('edited', edited)
          ..add('mistake', mistake)
          ..add('questionLabel', questionLabel)
          ..add('redInk', redInk)
          ..add('roundLabel', roundLabel))
        .toString();
  }
}

class ErrorCatalogEntryModelBuilder
    implements Builder<ErrorCatalogEntryModel, ErrorCatalogEntryModelBuilder> {
  _$ErrorCatalogEntryModel? _$v;

  String? _deduction;
  String? get deduction => _$this._deduction;
  set deduction(String? deduction) => _$this._deduction = deduction;

  bool? _edited;
  bool? get edited => _$this._edited;
  set edited(bool? edited) => _$this._edited = edited;

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

  ErrorCatalogEntryModelBuilder() {
    ErrorCatalogEntryModel._defaults(this);
  }

  ErrorCatalogEntryModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _deduction = $v.deduction;
      _edited = $v.edited;
      _mistake = $v.mistake;
      _questionLabel = $v.questionLabel;
      _redInk = $v.redInk;
      _roundLabel = $v.roundLabel;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ErrorCatalogEntryModel other) {
    _$v = other as _$ErrorCatalogEntryModel;
  }

  @override
  void update(void Function(ErrorCatalogEntryModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ErrorCatalogEntryModel build() => _build();

  _$ErrorCatalogEntryModel _build() {
    final _$result = _$v ??
        _$ErrorCatalogEntryModel._(
          deduction: deduction,
          edited: edited,
          mistake: BuiltValueNullFieldError.checkNotNull(
              mistake, r'ErrorCatalogEntryModel', 'mistake'),
          questionLabel: questionLabel,
          redInk: BuiltValueNullFieldError.checkNotNull(
              redInk, r'ErrorCatalogEntryModel', 'redInk'),
          roundLabel: roundLabel,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

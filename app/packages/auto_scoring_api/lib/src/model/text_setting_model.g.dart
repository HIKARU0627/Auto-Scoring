// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'text_setting_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TextSettingModel extends TextSettingModel {
  @override
  final String defaultValue;
  @override
  final String helpText;
  @override
  final String label;
  @override
  final String placeholder;
  @override
  final ConfigurationSource source_;
  @override
  final String value;
  @override
  final String variable;

  factory _$TextSettingModel(
          [void Function(TextSettingModelBuilder)? updates]) =>
      (TextSettingModelBuilder()..update(updates))._build();

  _$TextSettingModel._(
      {required this.defaultValue,
      required this.helpText,
      required this.label,
      required this.placeholder,
      required this.source_,
      required this.value,
      required this.variable})
      : super._();
  @override
  TextSettingModel rebuild(void Function(TextSettingModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TextSettingModelBuilder toBuilder() =>
      TextSettingModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TextSettingModel &&
        defaultValue == other.defaultValue &&
        helpText == other.helpText &&
        label == other.label &&
        placeholder == other.placeholder &&
        source_ == other.source_ &&
        value == other.value &&
        variable == other.variable;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, defaultValue.hashCode);
    _$hash = $jc(_$hash, helpText.hashCode);
    _$hash = $jc(_$hash, label.hashCode);
    _$hash = $jc(_$hash, placeholder.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, value.hashCode);
    _$hash = $jc(_$hash, variable.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TextSettingModel')
          ..add('defaultValue', defaultValue)
          ..add('helpText', helpText)
          ..add('label', label)
          ..add('placeholder', placeholder)
          ..add('source_', source_)
          ..add('value', value)
          ..add('variable', variable))
        .toString();
  }
}

class TextSettingModelBuilder
    implements Builder<TextSettingModel, TextSettingModelBuilder> {
  _$TextSettingModel? _$v;

  String? _defaultValue;
  String? get defaultValue => _$this._defaultValue;
  set defaultValue(String? defaultValue) => _$this._defaultValue = defaultValue;

  String? _helpText;
  String? get helpText => _$this._helpText;
  set helpText(String? helpText) => _$this._helpText = helpText;

  String? _label;
  String? get label => _$this._label;
  set label(String? label) => _$this._label = label;

  String? _placeholder;
  String? get placeholder => _$this._placeholder;
  set placeholder(String? placeholder) => _$this._placeholder = placeholder;

  ConfigurationSource? _source_;
  ConfigurationSource? get source_ => _$this._source_;
  set source_(ConfigurationSource? source_) => _$this._source_ = source_;

  String? _value;
  String? get value => _$this._value;
  set value(String? value) => _$this._value = value;

  String? _variable;
  String? get variable => _$this._variable;
  set variable(String? variable) => _$this._variable = variable;

  TextSettingModelBuilder() {
    TextSettingModel._defaults(this);
  }

  TextSettingModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _defaultValue = $v.defaultValue;
      _helpText = $v.helpText;
      _label = $v.label;
      _placeholder = $v.placeholder;
      _source_ = $v.source_;
      _value = $v.value;
      _variable = $v.variable;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TextSettingModel other) {
    _$v = other as _$TextSettingModel;
  }

  @override
  void update(void Function(TextSettingModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TextSettingModel build() => _build();

  _$TextSettingModel _build() {
    final _$result = _$v ??
        _$TextSettingModel._(
          defaultValue: BuiltValueNullFieldError.checkNotNull(
              defaultValue, r'TextSettingModel', 'defaultValue'),
          helpText: BuiltValueNullFieldError.checkNotNull(
              helpText, r'TextSettingModel', 'helpText'),
          label: BuiltValueNullFieldError.checkNotNull(
              label, r'TextSettingModel', 'label'),
          placeholder: BuiltValueNullFieldError.checkNotNull(
              placeholder, r'TextSettingModel', 'placeholder'),
          source_: BuiltValueNullFieldError.checkNotNull(
              source_, r'TextSettingModel', 'source_'),
          value: BuiltValueNullFieldError.checkNotNull(
              value, r'TextSettingModel', 'value'),
          variable: BuiltValueNullFieldError.checkNotNull(
              variable, r'TextSettingModel', 'variable'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

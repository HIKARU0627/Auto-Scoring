// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'intake_template_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$IntakeTemplateModel extends IntakeTemplateModel {
  @override
  final String id;
  @override
  final String name;
  @override
  final BuiltList<IntakeRuleModel> rules;
  @override
  final bool? splitChildDirectories;

  factory _$IntakeTemplateModel(
          [void Function(IntakeTemplateModelBuilder)? updates]) =>
      (IntakeTemplateModelBuilder()..update(updates))._build();

  _$IntakeTemplateModel._(
      {required this.id,
      required this.name,
      required this.rules,
      this.splitChildDirectories})
      : super._();
  @override
  IntakeTemplateModel rebuild(
          void Function(IntakeTemplateModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  IntakeTemplateModelBuilder toBuilder() =>
      IntakeTemplateModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is IntakeTemplateModel &&
        id == other.id &&
        name == other.name &&
        rules == other.rules &&
        splitChildDirectories == other.splitChildDirectories;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, name.hashCode);
    _$hash = $jc(_$hash, rules.hashCode);
    _$hash = $jc(_$hash, splitChildDirectories.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'IntakeTemplateModel')
          ..add('id', id)
          ..add('name', name)
          ..add('rules', rules)
          ..add('splitChildDirectories', splitChildDirectories))
        .toString();
  }
}

class IntakeTemplateModelBuilder
    implements Builder<IntakeTemplateModel, IntakeTemplateModelBuilder> {
  _$IntakeTemplateModel? _$v;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _name;
  String? get name => _$this._name;
  set name(String? name) => _$this._name = name;

  ListBuilder<IntakeRuleModel>? _rules;
  ListBuilder<IntakeRuleModel> get rules =>
      _$this._rules ??= ListBuilder<IntakeRuleModel>();
  set rules(ListBuilder<IntakeRuleModel>? rules) => _$this._rules = rules;

  bool? _splitChildDirectories;
  bool? get splitChildDirectories => _$this._splitChildDirectories;
  set splitChildDirectories(bool? splitChildDirectories) =>
      _$this._splitChildDirectories = splitChildDirectories;

  IntakeTemplateModelBuilder() {
    IntakeTemplateModel._defaults(this);
  }

  IntakeTemplateModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _id = $v.id;
      _name = $v.name;
      _rules = $v.rules.toBuilder();
      _splitChildDirectories = $v.splitChildDirectories;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(IntakeTemplateModel other) {
    _$v = other as _$IntakeTemplateModel;
  }

  @override
  void update(void Function(IntakeTemplateModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  IntakeTemplateModel build() => _build();

  _$IntakeTemplateModel _build() {
    _$IntakeTemplateModel _$result;
    try {
      _$result = _$v ??
          _$IntakeTemplateModel._(
            id: BuiltValueNullFieldError.checkNotNull(
                id, r'IntakeTemplateModel', 'id'),
            name: BuiltValueNullFieldError.checkNotNull(
                name, r'IntakeTemplateModel', 'name'),
            rules: rules.build(),
            splitChildDirectories: splitChildDirectories,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'rules';
        rules.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'IntakeTemplateModel', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

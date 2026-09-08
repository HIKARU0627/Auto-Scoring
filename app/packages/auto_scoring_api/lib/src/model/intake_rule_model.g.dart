// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'intake_rule_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$IntakeRuleModel extends IntakeRuleModel {
  @override
  final String pattern;
  @override
  final Requirement? requirement;
  @override
  final MaterialRole role;
  @override
  final RuleScope scope;

  factory _$IntakeRuleModel([void Function(IntakeRuleModelBuilder)? updates]) =>
      (IntakeRuleModelBuilder()..update(updates))._build();

  _$IntakeRuleModel._(
      {required this.pattern,
      this.requirement,
      required this.role,
      required this.scope})
      : super._();
  @override
  IntakeRuleModel rebuild(void Function(IntakeRuleModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  IntakeRuleModelBuilder toBuilder() => IntakeRuleModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is IntakeRuleModel &&
        pattern == other.pattern &&
        requirement == other.requirement &&
        role == other.role &&
        scope == other.scope;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, pattern.hashCode);
    _$hash = $jc(_$hash, requirement.hashCode);
    _$hash = $jc(_$hash, role.hashCode);
    _$hash = $jc(_$hash, scope.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'IntakeRuleModel')
          ..add('pattern', pattern)
          ..add('requirement', requirement)
          ..add('role', role)
          ..add('scope', scope))
        .toString();
  }
}

class IntakeRuleModelBuilder
    implements Builder<IntakeRuleModel, IntakeRuleModelBuilder> {
  _$IntakeRuleModel? _$v;

  String? _pattern;
  String? get pattern => _$this._pattern;
  set pattern(String? pattern) => _$this._pattern = pattern;

  Requirement? _requirement;
  Requirement? get requirement => _$this._requirement;
  set requirement(Requirement? requirement) =>
      _$this._requirement = requirement;

  MaterialRole? _role;
  MaterialRole? get role => _$this._role;
  set role(MaterialRole? role) => _$this._role = role;

  RuleScope? _scope;
  RuleScope? get scope => _$this._scope;
  set scope(RuleScope? scope) => _$this._scope = scope;

  IntakeRuleModelBuilder() {
    IntakeRuleModel._defaults(this);
  }

  IntakeRuleModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _pattern = $v.pattern;
      _requirement = $v.requirement;
      _role = $v.role;
      _scope = $v.scope;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(IntakeRuleModel other) {
    _$v = other as _$IntakeRuleModel;
  }

  @override
  void update(void Function(IntakeRuleModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  IntakeRuleModel build() => _build();

  _$IntakeRuleModel _build() {
    final _$result = _$v ??
        _$IntakeRuleModel._(
          pattern: BuiltValueNullFieldError.checkNotNull(
              pattern, r'IntakeRuleModel', 'pattern'),
          requirement: requirement,
          role: BuiltValueNullFieldError.checkNotNull(
              role, r'IntakeRuleModel', 'role'),
          scope: BuiltValueNullFieldError.checkNotNull(
              scope, r'IntakeRuleModel', 'scope'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

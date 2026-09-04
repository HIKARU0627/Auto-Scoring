// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'test_summary.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TestSummary extends TestSummary {
  @override
  final String id;
  @override
  final String name;
  @override
  final String? subject;

  factory _$TestSummary([void Function(TestSummaryBuilder)? updates]) =>
      (TestSummaryBuilder()..update(updates))._build();

  _$TestSummary._({required this.id, required this.name, this.subject})
      : super._();
  @override
  TestSummary rebuild(void Function(TestSummaryBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TestSummaryBuilder toBuilder() => TestSummaryBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TestSummary &&
        id == other.id &&
        name == other.name &&
        subject == other.subject;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, name.hashCode);
    _$hash = $jc(_$hash, subject.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TestSummary')
          ..add('id', id)
          ..add('name', name)
          ..add('subject', subject))
        .toString();
  }
}

class TestSummaryBuilder implements Builder<TestSummary, TestSummaryBuilder> {
  _$TestSummary? _$v;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _name;
  String? get name => _$this._name;
  set name(String? name) => _$this._name = name;

  String? _subject;
  String? get subject => _$this._subject;
  set subject(String? subject) => _$this._subject = subject;

  TestSummaryBuilder() {
    TestSummary._defaults(this);
  }

  TestSummaryBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _id = $v.id;
      _name = $v.name;
      _subject = $v.subject;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TestSummary other) {
    _$v = other as _$TestSummary;
  }

  @override
  void update(void Function(TestSummaryBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TestSummary build() => _build();

  _$TestSummary _build() {
    final _$result = _$v ??
        _$TestSummary._(
          id: BuiltValueNullFieldError.checkNotNull(id, r'TestSummary', 'id'),
          name: BuiltValueNullFieldError.checkNotNull(
              name, r'TestSummary', 'name'),
          subject: subject,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

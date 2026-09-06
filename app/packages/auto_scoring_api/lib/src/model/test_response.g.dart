// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'test_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TestResponse extends TestResponse {
  @override
  final DateTime createdAt;
  @override
  final String id;
  @override
  final String name;
  @override
  final String status;
  @override
  final String? subject;

  factory _$TestResponse([void Function(TestResponseBuilder)? updates]) =>
      (TestResponseBuilder()..update(updates))._build();

  _$TestResponse._(
      {required this.createdAt,
      required this.id,
      required this.name,
      required this.status,
      this.subject})
      : super._();
  @override
  TestResponse rebuild(void Function(TestResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TestResponseBuilder toBuilder() => TestResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TestResponse &&
        createdAt == other.createdAt &&
        id == other.id &&
        name == other.name &&
        status == other.status &&
        subject == other.subject;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, name.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, subject.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TestResponse')
          ..add('createdAt', createdAt)
          ..add('id', id)
          ..add('name', name)
          ..add('status', status)
          ..add('subject', subject))
        .toString();
  }
}

class TestResponseBuilder
    implements Builder<TestResponse, TestResponseBuilder> {
  _$TestResponse? _$v;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _name;
  String? get name => _$this._name;
  set name(String? name) => _$this._name = name;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  String? _subject;
  String? get subject => _$this._subject;
  set subject(String? subject) => _$this._subject = subject;

  TestResponseBuilder() {
    TestResponse._defaults(this);
  }

  TestResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _createdAt = $v.createdAt;
      _id = $v.id;
      _name = $v.name;
      _status = $v.status;
      _subject = $v.subject;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TestResponse other) {
    _$v = other as _$TestResponse;
  }

  @override
  void update(void Function(TestResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TestResponse build() => _build();

  _$TestResponse _build() {
    final _$result = _$v ??
        _$TestResponse._(
          createdAt: BuiltValueNullFieldError.checkNotNull(
              createdAt, r'TestResponse', 'createdAt'),
          id: BuiltValueNullFieldError.checkNotNull(id, r'TestResponse', 'id'),
          name: BuiltValueNullFieldError.checkNotNull(
              name, r'TestResponse', 'name'),
          status: BuiltValueNullFieldError.checkNotNull(
              status, r'TestResponse', 'status'),
          subject: subject,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

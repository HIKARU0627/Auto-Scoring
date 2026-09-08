// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'test_material_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$TestMaterialResponse extends TestMaterialResponse {
  @override
  final DateTime createdAt;
  @override
  final String id;
  @override
  final String? originalFilename;
  @override
  final MaterialRole role;
  @override
  final String sha256;
  @override
  final int sizeBytes;
  @override
  final String testId;

  factory _$TestMaterialResponse(
          [void Function(TestMaterialResponseBuilder)? updates]) =>
      (TestMaterialResponseBuilder()..update(updates))._build();

  _$TestMaterialResponse._(
      {required this.createdAt,
      required this.id,
      this.originalFilename,
      required this.role,
      required this.sha256,
      required this.sizeBytes,
      required this.testId})
      : super._();
  @override
  TestMaterialResponse rebuild(
          void Function(TestMaterialResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  TestMaterialResponseBuilder toBuilder() =>
      TestMaterialResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is TestMaterialResponse &&
        createdAt == other.createdAt &&
        id == other.id &&
        originalFilename == other.originalFilename &&
        role == other.role &&
        sha256 == other.sha256 &&
        sizeBytes == other.sizeBytes &&
        testId == other.testId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, originalFilename.hashCode);
    _$hash = $jc(_$hash, role.hashCode);
    _$hash = $jc(_$hash, sha256.hashCode);
    _$hash = $jc(_$hash, sizeBytes.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'TestMaterialResponse')
          ..add('createdAt', createdAt)
          ..add('id', id)
          ..add('originalFilename', originalFilename)
          ..add('role', role)
          ..add('sha256', sha256)
          ..add('sizeBytes', sizeBytes)
          ..add('testId', testId))
        .toString();
  }
}

class TestMaterialResponseBuilder
    implements Builder<TestMaterialResponse, TestMaterialResponseBuilder> {
  _$TestMaterialResponse? _$v;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _originalFilename;
  String? get originalFilename => _$this._originalFilename;
  set originalFilename(String? originalFilename) =>
      _$this._originalFilename = originalFilename;

  MaterialRole? _role;
  MaterialRole? get role => _$this._role;
  set role(MaterialRole? role) => _$this._role = role;

  String? _sha256;
  String? get sha256 => _$this._sha256;
  set sha256(String? sha256) => _$this._sha256 = sha256;

  int? _sizeBytes;
  int? get sizeBytes => _$this._sizeBytes;
  set sizeBytes(int? sizeBytes) => _$this._sizeBytes = sizeBytes;

  String? _testId;
  String? get testId => _$this._testId;
  set testId(String? testId) => _$this._testId = testId;

  TestMaterialResponseBuilder() {
    TestMaterialResponse._defaults(this);
  }

  TestMaterialResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _createdAt = $v.createdAt;
      _id = $v.id;
      _originalFilename = $v.originalFilename;
      _role = $v.role;
      _sha256 = $v.sha256;
      _sizeBytes = $v.sizeBytes;
      _testId = $v.testId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(TestMaterialResponse other) {
    _$v = other as _$TestMaterialResponse;
  }

  @override
  void update(void Function(TestMaterialResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  TestMaterialResponse build() => _build();

  _$TestMaterialResponse _build() {
    final _$result = _$v ??
        _$TestMaterialResponse._(
          createdAt: BuiltValueNullFieldError.checkNotNull(
              createdAt, r'TestMaterialResponse', 'createdAt'),
          id: BuiltValueNullFieldError.checkNotNull(
              id, r'TestMaterialResponse', 'id'),
          originalFilename: originalFilename,
          role: BuiltValueNullFieldError.checkNotNull(
              role, r'TestMaterialResponse', 'role'),
          sha256: BuiltValueNullFieldError.checkNotNull(
              sha256, r'TestMaterialResponse', 'sha256'),
          sizeBytes: BuiltValueNullFieldError.checkNotNull(
              sizeBytes, r'TestMaterialResponse', 'sizeBytes'),
          testId: BuiltValueNullFieldError.checkNotNull(
              testId, r'TestMaterialResponse', 'testId'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

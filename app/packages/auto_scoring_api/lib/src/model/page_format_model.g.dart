// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'page_format_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$PageFormatModel extends PageFormatModel {
  @override
  final num heightPt;
  @override
  final num widthPt;

  factory _$PageFormatModel([void Function(PageFormatModelBuilder)? updates]) =>
      (PageFormatModelBuilder()..update(updates))._build();

  _$PageFormatModel._({required this.heightPt, required this.widthPt})
      : super._();
  @override
  PageFormatModel rebuild(void Function(PageFormatModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  PageFormatModelBuilder toBuilder() => PageFormatModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is PageFormatModel &&
        heightPt == other.heightPt &&
        widthPt == other.widthPt;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, heightPt.hashCode);
    _$hash = $jc(_$hash, widthPt.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'PageFormatModel')
          ..add('heightPt', heightPt)
          ..add('widthPt', widthPt))
        .toString();
  }
}

class PageFormatModelBuilder
    implements Builder<PageFormatModel, PageFormatModelBuilder> {
  _$PageFormatModel? _$v;

  num? _heightPt;
  num? get heightPt => _$this._heightPt;
  set heightPt(num? heightPt) => _$this._heightPt = heightPt;

  num? _widthPt;
  num? get widthPt => _$this._widthPt;
  set widthPt(num? widthPt) => _$this._widthPt = widthPt;

  PageFormatModelBuilder() {
    PageFormatModel._defaults(this);
  }

  PageFormatModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _heightPt = $v.heightPt;
      _widthPt = $v.widthPt;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(PageFormatModel other) {
    _$v = other as _$PageFormatModel;
  }

  @override
  void update(void Function(PageFormatModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  PageFormatModel build() => _build();

  _$PageFormatModel _build() {
    final _$result = _$v ??
        _$PageFormatModel._(
          heightPt: BuiltValueNullFieldError.checkNotNull(
              heightPt, r'PageFormatModel', 'heightPt'),
          widthPt: BuiltValueNullFieldError.checkNotNull(
              widthPt, r'PageFormatModel', 'widthPt'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

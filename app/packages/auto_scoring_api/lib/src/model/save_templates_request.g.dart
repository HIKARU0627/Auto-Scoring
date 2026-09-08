// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'save_templates_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$SaveTemplatesRequest extends SaveTemplatesRequest {
  @override
  final BuiltList<IntakeTemplateModel> templates;

  factory _$SaveTemplatesRequest(
          [void Function(SaveTemplatesRequestBuilder)? updates]) =>
      (SaveTemplatesRequestBuilder()..update(updates))._build();

  _$SaveTemplatesRequest._({required this.templates}) : super._();
  @override
  SaveTemplatesRequest rebuild(
          void Function(SaveTemplatesRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  SaveTemplatesRequestBuilder toBuilder() =>
      SaveTemplatesRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is SaveTemplatesRequest && templates == other.templates;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, templates.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'SaveTemplatesRequest')
          ..add('templates', templates))
        .toString();
  }
}

class SaveTemplatesRequestBuilder
    implements Builder<SaveTemplatesRequest, SaveTemplatesRequestBuilder> {
  _$SaveTemplatesRequest? _$v;

  ListBuilder<IntakeTemplateModel>? _templates;
  ListBuilder<IntakeTemplateModel> get templates =>
      _$this._templates ??= ListBuilder<IntakeTemplateModel>();
  set templates(ListBuilder<IntakeTemplateModel>? templates) =>
      _$this._templates = templates;

  SaveTemplatesRequestBuilder() {
    SaveTemplatesRequest._defaults(this);
  }

  SaveTemplatesRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _templates = $v.templates.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(SaveTemplatesRequest other) {
    _$v = other as _$SaveTemplatesRequest;
  }

  @override
  void update(void Function(SaveTemplatesRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  SaveTemplatesRequest build() => _build();

  _$SaveTemplatesRequest _build() {
    _$SaveTemplatesRequest _$result;
    try {
      _$result = _$v ??
          _$SaveTemplatesRequest._(
            templates: templates.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'templates';
        templates.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'SaveTemplatesRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint

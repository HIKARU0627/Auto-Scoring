//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

import 'dart:async';

import 'package:built_value/json_object.dart';
import 'package:built_value/serializer.dart';
import 'package:dio/dio.dart';

import 'dart:typed_data';
import 'package:auto_scoring_api/src/api_util.dart';
import 'package:auto_scoring_api/src/model/document_pages_response.dart';
import 'package:auto_scoring_api/src/model/http_validation_error.dart';

class PagesApi {
  final Dio _dio;

  final Serializers _serializers;

  const PagesApi(this._dio, this._serializers);

  /// Get Answer Layout Page Image
  /// One page of the test&#39;s answer sheet, rasterized by the same pdfium that performs the coordinate transform (PoC 6, approach B).  **A normalized coordinate is built from the returned image&#39;s own pixel size, and from nothing else** (&#x60;normalized_x &#x3D; click_px / image_width_px&#x60;). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar&#39;s coordinate transform.  Do **not** divide by the &#x60;displayed_width&#x60; / &#x60;displayed_height&#x60; reported by &#x60;GET .../pages&#x60;. The image&#39;s pixel size is rounded up independently (&#x60;ceil(displayed x scale)&#x60;), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.
  ///
  /// Parameters:
  /// * [testId]
  /// * [pageIndex] - 0-based page index.
  /// * [scale] - Pixels per PDF point. Only 1.0, 2.0 and 3.5 are accepted; any other value is rejected with 422 rather than snapped to a permitted one.
  /// * [cancelToken] - A [CancelToken] that can be used to cancel the operation
  /// * [headers] - Can be used to add additional headers to the request
  /// * [extras] - Can be used to add flags to the request
  /// * [validateStatus] - A [ValidateStatus] callback that can be used to determine request success based on the HTTP status of the response
  /// * [onSendProgress] - A [ProgressCallback] that can be used to get the send progress
  /// * [onReceiveProgress] - A [ProgressCallback] that can be used to get the receive progress
  ///
  /// Returns a [Future] containing a [Response] with a [Uint8List] as data
  /// Throws [DioException] if API call or serialization fails
  Future<Response<Uint8List>>
      getAnswerLayoutPageImageTestsTestIdAnswerLayoutPagesPageIndexImageGet({
    required String testId,
    required int pageIndex,
    num? scale = 2.0,
    CancelToken? cancelToken,
    Map<String, dynamic>? headers,
    Map<String, dynamic>? extra,
    ValidateStatus? validateStatus,
    ProgressCallback? onSendProgress,
    ProgressCallback? onReceiveProgress,
  }) async {
    final _path = r'/tests/{test_id}/answer-layout/pages/{page_index}/image'
        .replaceAll(
            '{' r'test_id' '}',
            encodeQueryParameter(_serializers, testId, const FullType(String))
                .toString())
        .replaceAll(
            '{' r'page_index' '}',
            encodeQueryParameter(_serializers, pageIndex, const FullType(int))
                .toString());
    final _options = Options(
      method: r'GET',
      responseType: ResponseType.bytes,
      headers: <String, dynamic>{
        ...?headers,
      },
      extra: <String, dynamic>{
        'secure': <Map<String, String>>[
          {
            'type': 'http',
            'scheme': 'bearer',
            'name': 'HTTPBearer',
          },
        ],
        ...?extra,
      },
      validateStatus: validateStatus,
    );

    final _queryParameters = <String, dynamic>{
      if (scale != null)
        r'scale':
            encodeQueryParameter(_serializers, scale, const FullType(num)),
    };

    final _response = await _dio.request<Object>(
      _path,
      options: _options,
      queryParameters: _queryParameters,
      cancelToken: cancelToken,
      onSendProgress: onSendProgress,
      onReceiveProgress: onReceiveProgress,
    );

    Uint8List? _responseData;

    try {
      final rawResponse = _response.data;
      _responseData = rawResponse == null ? null : rawResponse as Uint8List;
    } catch (error, stackTrace) {
      throw DioException(
        requestOptions: _response.requestOptions,
        response: _response,
        type: DioExceptionType.unknown,
        error: error,
        stackTrace: stackTrace,
      );
    }

    return Response<Uint8List>(
      data: _responseData,
      headers: _response.headers,
      isRedirect: _response.isRedirect,
      requestOptions: _response.requestOptions,
      redirects: _response.redirects,
      statusCode: _response.statusCode,
      statusMessage: _response.statusMessage,
      extra: _response.extra,
    );
  }

  /// Get Submission Page Image
  /// One page of the answer PDF, rasterized by the same pdfium that performs the coordinate transform (PoC 6, approach B).  **A normalized coordinate is built from the returned image&#39;s own pixel size, and from nothing else** (&#x60;normalized_x &#x3D; click_px / image_width_px&#x60;). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar&#39;s coordinate transform.  Do **not** divide by the &#x60;displayed_width&#x60; / &#x60;displayed_height&#x60; reported by &#x60;GET .../pages&#x60;. The image&#39;s pixel size is rounded up independently (&#x60;ceil(displayed x scale)&#x60;), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.
  ///
  /// Parameters:
  /// * [submissionId]
  /// * [pageIndex] - 0-based page index.
  /// * [scale] - Pixels per PDF point. Only 1.0, 2.0 and 3.5 are accepted; any other value is rejected with 422 rather than snapped to a permitted one.
  /// * [cancelToken] - A [CancelToken] that can be used to cancel the operation
  /// * [headers] - Can be used to add additional headers to the request
  /// * [extras] - Can be used to add flags to the request
  /// * [validateStatus] - A [ValidateStatus] callback that can be used to determine request success based on the HTTP status of the response
  /// * [onSendProgress] - A [ProgressCallback] that can be used to get the send progress
  /// * [onReceiveProgress] - A [ProgressCallback] that can be used to get the receive progress
  ///
  /// Returns a [Future] containing a [Response] with a [Uint8List] as data
  /// Throws [DioException] if API call or serialization fails
  Future<Response<Uint8List>>
      getSubmissionPageImageSubmissionsSubmissionIdPagesPageIndexImageGet({
    required String submissionId,
    required int pageIndex,
    num? scale = 2.0,
    CancelToken? cancelToken,
    Map<String, dynamic>? headers,
    Map<String, dynamic>? extra,
    ValidateStatus? validateStatus,
    ProgressCallback? onSendProgress,
    ProgressCallback? onReceiveProgress,
  }) async {
    final _path = r'/submissions/{submission_id}/pages/{page_index}/image'
        .replaceAll(
            '{' r'submission_id' '}',
            encodeQueryParameter(
                    _serializers, submissionId, const FullType(String))
                .toString())
        .replaceAll(
            '{' r'page_index' '}',
            encodeQueryParameter(_serializers, pageIndex, const FullType(int))
                .toString());
    final _options = Options(
      method: r'GET',
      responseType: ResponseType.bytes,
      headers: <String, dynamic>{
        ...?headers,
      },
      extra: <String, dynamic>{
        'secure': <Map<String, String>>[
          {
            'type': 'http',
            'scheme': 'bearer',
            'name': 'HTTPBearer',
          },
        ],
        ...?extra,
      },
      validateStatus: validateStatus,
    );

    final _queryParameters = <String, dynamic>{
      if (scale != null)
        r'scale':
            encodeQueryParameter(_serializers, scale, const FullType(num)),
    };

    final _response = await _dio.request<Object>(
      _path,
      options: _options,
      queryParameters: _queryParameters,
      cancelToken: cancelToken,
      onSendProgress: onSendProgress,
      onReceiveProgress: onReceiveProgress,
    );

    Uint8List? _responseData;

    try {
      final rawResponse = _response.data;
      _responseData = rawResponse == null ? null : rawResponse as Uint8List;
    } catch (error, stackTrace) {
      throw DioException(
        requestOptions: _response.requestOptions,
        response: _response,
        type: DioExceptionType.unknown,
        error: error,
        stackTrace: stackTrace,
      );
    }

    return Response<Uint8List>(
      data: _responseData,
      headers: _response.headers,
      isRedirect: _response.isRedirect,
      requestOptions: _response.requestOptions,
      redirects: _response.redirects,
      statusCode: _response.statusCode,
      statusMessage: _response.statusMessage,
      extra: _response.extra,
    );
  }

  /// List Answer Layout Pages
  /// Page count, displayed size and rotation of the test&#39;s answer sheet, for laying the answer-area editor out **before** the page images arrive, and for paging.  **A normalized coordinate is built from the returned image&#39;s own pixel size, and from nothing else** (&#x60;normalized_x &#x3D; click_px / image_width_px&#x60;). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar&#39;s coordinate transform.  Do **not** divide by the &#x60;displayed_width&#x60; / &#x60;displayed_height&#x60; reported by &#x60;GET .../pages&#x60;. The image&#39;s pixel size is rounded up independently (&#x60;ceil(displayed x scale)&#x60;), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.
  ///
  /// Parameters:
  /// * [testId]
  /// * [cancelToken] - A [CancelToken] that can be used to cancel the operation
  /// * [headers] - Can be used to add additional headers to the request
  /// * [extras] - Can be used to add flags to the request
  /// * [validateStatus] - A [ValidateStatus] callback that can be used to determine request success based on the HTTP status of the response
  /// * [onSendProgress] - A [ProgressCallback] that can be used to get the send progress
  /// * [onReceiveProgress] - A [ProgressCallback] that can be used to get the receive progress
  ///
  /// Returns a [Future] containing a [Response] with a [DocumentPagesResponse] as data
  /// Throws [DioException] if API call or serialization fails
  Future<Response<DocumentPagesResponse>>
      listAnswerLayoutPagesTestsTestIdAnswerLayoutPagesGet({
    required String testId,
    CancelToken? cancelToken,
    Map<String, dynamic>? headers,
    Map<String, dynamic>? extra,
    ValidateStatus? validateStatus,
    ProgressCallback? onSendProgress,
    ProgressCallback? onReceiveProgress,
  }) async {
    final _path = r'/tests/{test_id}/answer-layout/pages'.replaceAll(
        '{' r'test_id' '}',
        encodeQueryParameter(_serializers, testId, const FullType(String))
            .toString());
    final _options = Options(
      method: r'GET',
      headers: <String, dynamic>{
        ...?headers,
      },
      extra: <String, dynamic>{
        'secure': <Map<String, String>>[
          {
            'type': 'http',
            'scheme': 'bearer',
            'name': 'HTTPBearer',
          },
        ],
        ...?extra,
      },
      validateStatus: validateStatus,
    );

    final _response = await _dio.request<Object>(
      _path,
      options: _options,
      cancelToken: cancelToken,
      onSendProgress: onSendProgress,
      onReceiveProgress: onReceiveProgress,
    );

    DocumentPagesResponse? _responseData;

    try {
      final rawResponse = _response.data;
      _responseData = rawResponse == null
          ? null
          : _serializers.deserialize(
              rawResponse,
              specifiedType: const FullType(DocumentPagesResponse),
            ) as DocumentPagesResponse;
    } catch (error, stackTrace) {
      throw DioException(
        requestOptions: _response.requestOptions,
        response: _response,
        type: DioExceptionType.unknown,
        error: error,
        stackTrace: stackTrace,
      );
    }

    return Response<DocumentPagesResponse>(
      data: _responseData,
      headers: _response.headers,
      isRedirect: _response.isRedirect,
      requestOptions: _response.requestOptions,
      redirects: _response.redirects,
      statusCode: _response.statusCode,
      statusMessage: _response.statusMessage,
      extra: _response.extra,
    );
  }

  /// List Submission Pages
  /// Page count, displayed size and rotation of the answer PDF, for laying the viewer out **before** the page images arrive, and for paging.  **A normalized coordinate is built from the returned image&#39;s own pixel size, and from nothing else** (&#x60;normalized_x &#x3D; click_px / image_width_px&#x60;). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar&#39;s coordinate transform.  Do **not** divide by the &#x60;displayed_width&#x60; / &#x60;displayed_height&#x60; reported by &#x60;GET .../pages&#x60;. The image&#39;s pixel size is rounded up independently (&#x60;ceil(displayed x scale)&#x60;), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.
  ///
  /// Parameters:
  /// * [submissionId]
  /// * [cancelToken] - A [CancelToken] that can be used to cancel the operation
  /// * [headers] - Can be used to add additional headers to the request
  /// * [extras] - Can be used to add flags to the request
  /// * [validateStatus] - A [ValidateStatus] callback that can be used to determine request success based on the HTTP status of the response
  /// * [onSendProgress] - A [ProgressCallback] that can be used to get the send progress
  /// * [onReceiveProgress] - A [ProgressCallback] that can be used to get the receive progress
  ///
  /// Returns a [Future] containing a [Response] with a [DocumentPagesResponse] as data
  /// Throws [DioException] if API call or serialization fails
  Future<Response<DocumentPagesResponse>>
      listSubmissionPagesSubmissionsSubmissionIdPagesGet({
    required String submissionId,
    CancelToken? cancelToken,
    Map<String, dynamic>? headers,
    Map<String, dynamic>? extra,
    ValidateStatus? validateStatus,
    ProgressCallback? onSendProgress,
    ProgressCallback? onReceiveProgress,
  }) async {
    final _path = r'/submissions/{submission_id}/pages'.replaceAll(
        '{' r'submission_id' '}',
        encodeQueryParameter(_serializers, submissionId, const FullType(String))
            .toString());
    final _options = Options(
      method: r'GET',
      headers: <String, dynamic>{
        ...?headers,
      },
      extra: <String, dynamic>{
        'secure': <Map<String, String>>[
          {
            'type': 'http',
            'scheme': 'bearer',
            'name': 'HTTPBearer',
          },
        ],
        ...?extra,
      },
      validateStatus: validateStatus,
    );

    final _response = await _dio.request<Object>(
      _path,
      options: _options,
      cancelToken: cancelToken,
      onSendProgress: onSendProgress,
      onReceiveProgress: onReceiveProgress,
    );

    DocumentPagesResponse? _responseData;

    try {
      final rawResponse = _response.data;
      _responseData = rawResponse == null
          ? null
          : _serializers.deserialize(
              rawResponse,
              specifiedType: const FullType(DocumentPagesResponse),
            ) as DocumentPagesResponse;
    } catch (error, stackTrace) {
      throw DioException(
        requestOptions: _response.requestOptions,
        response: _response,
        type: DioExceptionType.unknown,
        error: error,
        stackTrace: stackTrace,
      );
    }

    return Response<DocumentPagesResponse>(
      data: _responseData,
      headers: _response.headers,
      isRedirect: _response.isRedirect,
      requestOptions: _response.requestOptions,
      redirects: _response.redirects,
      statusCode: _response.statusCode,
      statusMessage: _response.statusMessage,
      extra: _response.extra,
    );
  }
}

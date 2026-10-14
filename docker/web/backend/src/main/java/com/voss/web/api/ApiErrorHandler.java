// REST API 오류를 공통 JSON 응답으로 바꾼다.
// 입력: 계약 오류. 출력: ok=false, message, detail JSON.
// 근거: docs/interfaces/web_api.md.
package com.voss.web.api;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {
    /** 계약 오류를 HTTP 상태 및 JSON 코드로 반환한다. */
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String,Object>> handleApiError(ApiException error) {
        return ResponseEntity.status(error.status()).body(Map.of(
                "ok", false, "message", error.code(), "detail", error.getMessage()));
    }

    /** JSON 파싱·필수 파라미터 오류를 INVALID_QUERY로 통일한다. */
    @ExceptionHandler({HttpMessageNotReadableException.class,
            MissingServletRequestParameterException.class,
            MethodArgumentTypeMismatchException.class})
    public ResponseEntity<Map<String,Object>> handleBadRequest(Exception error) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of(
                "ok", false, "message", "INVALID_QUERY", "detail", "요청 형식 또는 인자가 올바르지 않습니다."));
    }
}

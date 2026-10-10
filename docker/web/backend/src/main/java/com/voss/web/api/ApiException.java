// 웹 API 실패를 web_api.md 공통 오류 형식으로 변환할 때 쓰는 예외.
// 입력: HTTP 상태 및 계약 오류 코드. 출력: 일관된 API 오류 응답.
// 근거: docs/interfaces/web_api.md.
package com.voss.web.api;

import org.springframework.http.HttpStatus;

public class ApiException extends RuntimeException {
    private final HttpStatus status;
    private final String code;

    /** 오류의 HTTP 상태와 계약 코드를 보관한다. */
    public ApiException(HttpStatus status, String code, String detail) {
        super(detail);
        this.status = status;
        this.code = code;
    }

    /** HTTP 오류 상태를 반환한다. */
    public HttpStatus status() { return status; }

    /** 계약에 정의된 오류 코드를 반환한다. */
    public String code() { return code; }
}

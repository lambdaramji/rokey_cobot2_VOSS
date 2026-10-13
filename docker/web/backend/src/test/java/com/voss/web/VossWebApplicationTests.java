// T13 #22 Spring Boot 애플리케이션의 기본 설정을 검증한다.
// 입력: Spring Boot 애플리케이션 설정 및 컨텍스트.
// 출력: JUnit 테스트의 통과 또는 실패 결과.
// 근거: ADR-0006, docs/interfaces/web_api.md.

package com.voss.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class VossWebApplicationTests {

    @Autowired
    private ApplicationContext applicationContext;

    @Value("${server.address}")
    private String serverAddress;

    @Value("${server.port}")
    private int serverPort;

    /**
     * Spring Boot 애플리케이션 구성이 정상적으로 로드되는지 확인한다.
     * 실제 HTTP 서버는 실행하지 않는다.
     */
    @Test
    void applicationContextLoadsWithoutStartingHttpServer() {
        assertNotNull(applicationContext);
    }

    /**
     * 웹 API 계약에 지정된 로컬 바인딩과 포트를 확인한다.
     * 실제 네트워크 포트의 개방 여부는 검사하지 않는다.
     */
    @Test
    void serverUsesLocalBindingAndContractPort() {
        assertEquals("127.0.0.1", serverAddress);
        assertEquals(8080, serverPort);
    }
}
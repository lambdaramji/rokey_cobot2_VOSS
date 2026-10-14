// T13 #22 웹 HMI용 Spring Boot 애플리케이션을 시작한다.
// 입력: Java 프로그램 실행 인자.
// 출력: Spring Boot 웹 애플리케이션 실행.
// 근거: ADR-0006, docs/interfaces/web_api.md

package com.voss.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class VossWebApplication {

    /**
     * Spring Boot 웹 애플리케이션을 시작한다.
     * 초기화에 실패하면 애플리케이션 실행에 실패한다.
     *
     * @param args 프로그램 실행 인자
     */
    public static void main(String[] args) {
        SpringApplication.run(VossWebApplication.class, args);
    }
}
// Spring Integration MQTT 연결 상태 이벤트를 SSE link로 중계한다.
// 입력: MQTT 어댑터 연결·구독 이벤트. 출력: UP·DOWN 링크 상태.
// 근거: docs/interfaces/web_api.md link 이벤트, mqtt.md.
package com.voss.web.mqtt;

import com.voss.web.service.LiveEvents;
import com.voss.web.service.MqttLinkStatusStore;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class MqttConnectionEvents {
    private final MqttLinkStatusStore links;
    private final LiveEvents events;

    /** 연결 상태 저장소와 SSE 구독자를 전달받는다. */
    public MqttConnectionEvents(MqttLinkStatusStore links, LiveEvents events) {
        this.links = links;
        this.events = events;
    }

    /** MQTT 구독 확인·연결 실패 이벤트만 처리하고 나머지는 무시한다. */
    @EventListener
    public void onIntegrationEvent(ApplicationEvent event) {
        String eventName = event.getClass().getSimpleName();
        if ("MqttSubscribedEvent".equals(eventName)) {
            links.markConnected();
            events.publishLink();
            return;
        }
        if ("MqttConnectionFailedEvent".equals(eventName)
                || "MqttConnectionLostEvent".equals(eventName)) {
            links.markDisconnected();
            events.publishLink();
        }
    }
}

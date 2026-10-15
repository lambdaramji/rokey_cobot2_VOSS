import { useEffect, useRef, useState } from 'react';

/** 카메라 메뉴를 열면 프레임 조회를 시작하고 실패 시 자동 재시도한다. */
export function GripperCameraPanel() {
  const [live, setLive] = useState(false);
  const [message, setMessage] = useState('영상 연결 대기 · 자동 재시도 중');
  const image = useRef<HTMLImageElement>(null);

  useEffect(() => {
    let active = true;
    let objectUrl = '';
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;

    async function update() {
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 3000);

      try {
        const response = await fetch('/camera/gripper/frame.jpg', {
          cache: 'no-store',
          signal: controller.signal,
        });

        if (response.status === 502 || response.status === 504) {
          throw new Error('Nodes PC의 8091 카메라 송출에 연결할 수 없습니다. camera_preview 실행을 확인해 주세요.');
        }
        if (response.status === 503) {
          throw new Error('Nodes PC에서 새 카메라 프레임을 기다리는 중입니다.');
        }
        if (response.status === 403) {
          throw new Error('그리퍼 영상 접근이 거부되었습니다.');
        }
        if (!response.ok || !response.headers.get('content-type')?.startsWith('image/jpeg')) {
          throw new Error('그리퍼 영상 응답을 확인할 수 없습니다.');
        }

        const blob = await response.blob();
        if (!active) return;

        const next = URL.createObjectURL(blob);
        if (image.current) image.current.src = next;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = next;
      } catch (error) {
        if (active) {
          setLive(false);
          setMessage(error instanceof Error ? error.message : '영상 연결 대기 · 자동 재시도 중');
          image.current?.removeAttribute('src');
        }
      } finally {
        window.clearTimeout(timeout);
        if (active) timer = setTimeout(() => void update(), 200);
      }
    }

    void update();

    return () => {
      active = false;
      clearTimeout(timer);
      controller?.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      image.current?.removeAttribute('src');
    };
  }, []);

  return <section className="panel camera-panel">
    <div className="section-heading">
      <div>
        <span className="eyebrow">CAMERA / NODES PC</span>
        <h2>그리퍼 카메라</h2>
      </div>
      <span className={`chip ${live ? '' : 'warning'}`}>
        {live ? 'LIVE' : 'OFFLINE'}
      </span>
    </div>

    <div className="camera-preview">
      <img
        ref={image}
        alt="그리퍼 카메라 영상과 박스 검출 영역"
        hidden={!live}
        onLoad={() => setLive(true)}
        onError={() => setLive(false)}
      />
      {!live && <span>{message}</span>}
    </div>
    <p className="inline-notice" role="status">
      {live
        ? '초록색 바운딩 박스의 T 번호는 비전 트랙 번호입니다. 분류 이력의 BOX 번호와 다릅니다. 옆의 %는 송장 채움 판정값(80% 이상 통과)이며 인식 신뢰도가 아닙니다.'
        : message}
    </p>
  </section>;
}

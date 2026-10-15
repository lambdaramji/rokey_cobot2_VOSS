import { useEffect, useRef, useState } from 'react';

const CAMERA_NAME = 'C270 HD WEBCAM';

/** Nodes PC가 송출한 C270 영상만 표시한다. 페이지 재진입 때도 자동 연결한다. */
export function UsbCameraPanel() {
  const image = useRef<HTMLImageElement>(null);
  const [selected, setSelected] = useState('c270');
  const [live, setLive] = useState(false);
  const [message, setMessage] = useState('Nodes PC 카메라 연결 대기 · 자동 재시도 중');

  useEffect(() => {
    if (selected !== 'c270') {
      setLive(false);
      return;
    }
    let active = true;
    let objectUrl = '';
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | undefined;
    async function update() {
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller?.abort(), 3000);
      try {
        const response = await fetch('/camera/usb/frame.jpg', { cache: 'no-store', signal: controller.signal });
        if (response.status === 502 || response.status === 504) throw new Error('Nodes PC의 8092 카메라 송출에 연결할 수 없습니다.');
        if (response.status === 503) throw new Error('Nodes PC에서 C270 영상 프레임을 기다리는 중입니다.');
        if (response.status === 403) throw new Error('카메라 영상 접근이 거부되었습니다.');
        if (!response.ok || !response.headers.get('content-type')?.startsWith('image/jpeg')) throw new Error('C270 영상 응답을 확인할 수 없습니다.');
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
        if (active) timer = setTimeout(() => void update(), 250);
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
  }, [selected]);

  return <section className="panel camera-panel">
    <div className="section-heading"><div><span className="eyebrow">CAMERA / NODES PC</span><h2>{CAMERA_NAME}</h2></div><span className={`chip ${live ? '' : 'warning'}`}>{live ? 'LIVE' : 'OFFLINE'}</span></div>
    <div className="camera-preview">
      <img ref={image} alt={`${CAMERA_NAME} 실시간 영상`} hidden={!live} onLoad={() => setLive(true)} onError={() => setLive(false)} />
      {!live && <span role="status">{message}</span>}
    </div>
    <div className="field camera-device-field">
      <label htmlFor="usb-camera">USB 카메라</label>
      <div className="inline-input"><select id="usb-camera" value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">카메라 선택</option>
        <option value="c270">{CAMERA_NAME}</option>
      </select></div>
    </div>
  </section>;
}

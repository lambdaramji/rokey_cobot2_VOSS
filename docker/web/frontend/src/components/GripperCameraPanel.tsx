import { useEffect, useRef, useState } from 'react';

/** Poll complete JPEG frames: overlays are rendered against matching ROS timestamps. */
export function GripperCameraPanel() {
  const [enabled, setEnabled] = useState(false);
  const [live, setLive] = useState(false);
  const image = useRef<HTMLImageElement>(null);
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    let objectUrl = '';
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    async function update() {
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 3000);
      try {
        const response = await fetch('/camera/gripper/frame.jpg', { cache: 'no-store', signal: controller.signal });
        if (!response.ok || !response.headers.get('content-type')?.startsWith('image/jpeg')) throw new Error('No frame');
        const blob = await response.blob();
        if (!active) return;
        const next = URL.createObjectURL(blob);
        if (image.current) image.current.src = next;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = next;
      } catch {
        if (active) {
          setLive(false);
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
  }, [enabled]);

  return <section className="panel camera-panel">
    <div className="section-heading"><div><span className="eyebrow">CAMERA / NODES PC</span><h2>그리퍼 카메라</h2></div><span className={`chip ${live ? '' : 'warning'}`}>{live ? 'LIVE' : 'OFFLINE'}</span></div>
    <div className="camera-preview">
      <img ref={image} alt="그리퍼 카메라 영상과 박스 검출 영역" hidden={!live} onLoad={() => setLive(true)} onError={() => setLive(false)} />
      {!live && <span>{enabled ? '영상 연결 대기 · 자동 재시도 중' : '그리퍼 카메라 영상 대기'}</span>}
    </div>
    <button type="button" className="action camera-connect" onClick={() => { setLive(false); setEnabled(value => !value); }}>{enabled ? '연결 종료' : '영상 연결'}</button>
    <p className="inline-notice" role="status">{live ? '초록색 바운딩 박스의 T 번호는 비전 트랙 번호입니다. 분류 이력의 BOX 번호와 다릅니다.' : enabled ? 'Nodes PC의 카메라 송출 노드와 Web PC 연결 경로를 확인해 주세요.' : 'Nodes PC의 그리퍼 카메라와 박스 검출 결과를 표시합니다.'}</p>
  </section>;
}

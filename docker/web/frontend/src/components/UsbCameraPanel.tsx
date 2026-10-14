import { useEffect, useRef, useState } from 'react';

function cameraError(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError' || error.name === 'SecurityError') return '카메라 권한이 차단됐습니다. 브라우저에서 카메라 접근을 허용해 주세요.';
    if (error.name === 'NotFoundError' || error.name === 'OverconstrainedError') return '선택한 카메라를 찾을 수 없습니다. USB 연결과 카메라 선택을 확인해 주세요.';
    if (error.name === 'NotReadableError' || error.name === 'AbortError') return '카메라를 열 수 없습니다. 연결 상태와 다른 앱의 사용 여부를 확인해 주세요.';
  }
  return '영상을 표시할 수 없습니다. 카메라 연결을 확인하고 다시 시도해 주세요.';
}

/** 브라우저를 실행하는 Web PC의 카메라를 표시한다. 영상과 음성을 서버로 보내지 않는다. */
export function UsbCameraPanel() {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const request = useRef(0);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [message, setMessage] = useState('Web PC에 USB 카메라를 연결하고 아래 버튼을 눌러 주세요.');

  function releaseStream() {
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    if (video.current) video.current.srcObject = null;
  }

  useEffect(() => {
    let active = true;
    const media = navigator.mediaDevices;
    async function refreshDevices() {
      try {
        const inputs = await media?.enumerateDevices();
        if (!active || !inputs) return;
        const cameras = inputs.filter(device => device.kind === 'videoinput');
        setDevices(cameras);
        if (stream.current?.getVideoTracks().every(track => track.readyState === 'ended')) {
          request.current += 1;
          releaseStream();
          setLive(false);
          setBusy(false);
          setMessage('카메라 연결이 끊겼습니다. USB를 확인하고 다시 연결해 주세요.');
        } else if (cameras.length === 0 && !stream.current) {
          setMessage('연결된 카메라가 없습니다. USB 연결을 확인해 주세요.');
        }
      } catch {
        if (active && !stream.current) setMessage('카메라 연결 상태를 확인할 수 없습니다. 브라우저 권한을 확인해 주세요.');
      }
    }
    void refreshDevices();
    media?.addEventListener('devicechange', refreshDevices);
    return () => {
      active = false;
      request.current += 1;
      releaseStream();
      media?.removeEventListener('devicechange', refreshDevices);
    };
  }, []);

  async function connect() {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setMessage('Web PC에서 http://localhost로 접속하거나 HTTPS 주소를 사용해 주세요. 현재 주소에서는 카메라 접근이 지원되지 않습니다.');
      return;
    }
    const id = ++request.current;
    releaseStream();
    setLive(false);
    setBusy(true);
    setMessage('브라우저의 카메라 권한을 허용해 주세요.');
    try {
      const next = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { ...(selected ? { deviceId: { exact: selected } } : {}), width: { ideal: 1280 }, height: { ideal: 720 } },
      });
      if (id !== request.current) {
        next.getTracks().forEach(track => track.stop());
        return;
      }
      stream.current = next;
      const track = next.getVideoTracks()[0];
      track.addEventListener('ended', () => {
        if (stream.current !== next) return;
        request.current += 1;
        releaseStream();
        setLive(false);
        setBusy(false);
        setMessage('카메라 연결이 끊겼습니다. USB를 확인하고 다시 연결해 주세요.');
      });
      if (video.current) {
        video.current.srcObject = next;
        await video.current.play();
      }
      if (id !== request.current) return;
      setLive(true);
      setSelected(track.getSettings().deviceId ?? '');
      setMessage(track.label || '카메라 연결됨');
      try {
        const inputs = await navigator.mediaDevices.enumerateDevices();
        if (id === request.current) setDevices(inputs.filter(device => device.kind === 'videoinput'));
      } catch { /* 영상 연결은 장치 목록 조회 실패와 무관하게 유지한다. */ }
    } catch (error) {
      if (id !== request.current) return;
      releaseStream();
      setLive(false);
      setMessage(cameraError(error));
    } finally {
      if (id === request.current) setBusy(false);
    }
  }

  function disconnect() {
    request.current += 1;
    releaseStream();
    setBusy(false);
    setLive(false);
    setMessage('카메라 연결을 종료했습니다.');
  }

  return <section className="panel camera-panel">
    <div className="section-heading"><div><span className="eyebrow">CAMERA / WEB PC</span><h2>USB 카메라</h2></div><span className={`chip ${live ? '' : 'warning'}`}>{live ? 'LIVE' : 'OFFLINE'}</span></div>
    <div className="camera-preview">
      <video ref={video} muted playsInline aria-label="Web PC USB 카메라 실시간 영상" />
      {!live && <span>{busy ? '카메라 연결 중' : '카메라 영상 대기'}</span>}
    </div>
    <div className="field camera-controls">
      <label htmlFor="usb-camera">카메라 선택</label>
      <div className="inline-input"><select id="usb-camera" value={selected} disabled={busy} onChange={event => setSelected(event.target.value)}>
        <option value="">기본 카메라</option>
        {devices.filter(device => device.deviceId).map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `카메라 ${index + 1}`}</option>)}
      </select><button disabled={busy} onClick={() => void connect()}>{live ? '카메라 변경' : '카메라 연결'}</button>
      {(live || busy) && <button onClick={disconnect}>{busy ? '취소' : '연결 종료'}</button>}</div>
    </div>
    <p className="inline-notice" role="status">{message}</p>
  </section>;
}

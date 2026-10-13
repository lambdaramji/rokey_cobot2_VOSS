// S2-T08: 팔레트 3D 화면 DOM 반영 시각 관측 — 공용 PC 브라우저(F12 Console)에 붙여 넣는다.
// 입력: React 팔레트 패널의 data-pallet-key 변화. 출력: vossPalletReport(SENT_JSON 배열) → 키별 지연·p95·최대·판정.
// 같은 공용 PC 시계(ROS 재생기와 브라우저)라 시계 보정이 없다. 근거: web_api.md pallet_state, plan.md S2-T08(반영 ≤ 1초).
(() => {
  const panel = document.querySelector('[data-testid="pallet-panel"]');
  if (!panel) { console.error('팔레트 패널이 없습니다. HMI 화면(http://127.0.0.1/)에서 실행하세요.'); return; }
  const seen = new Map();
  const record = () => { const key = panel.getAttribute('data-pallet-key'); if (key && !seen.has(key)) seen.set(key, Date.now()); };
  new MutationObserver(record).observe(panel, { attributes: true, attributeFilter: ['data-pallet-key'] });
  window.vossPalletReport = (sent) => {
    const rows = sent.map(([key, sentMs], i) => {
      const domMs = seen.get(key);
      return { i: i + 1, key: key.split('|').slice(1, 5).join('|'), latency_ms: domMs === undefined ? null : domMs - sentMs };
    });
    console.table(rows);
    const got = rows.map(r => r.latency_ms).filter(v => v !== null).sort((a, b) => a - b);
    const missing = rows.length - got.length;
    const p95 = got.length ? got[Math.min(got.length - 1, Math.ceil(got.length * 0.95) - 1)] : null;
    const max = got.length ? got[got.length - 1] : null;
    const pass = missing === 0 && max !== null && max <= 1000;
    console.log(`수신 ${got.length}/${rows.length} · p95 ${p95} ms · 최대 ${max} ms · 판정 ${pass ? 'PASS (≤ 1000 ms)' : 'FAIL'}`);
    return { rows, p95, max, missing, pass };
  };
  console.log('S2-T08 관측 준비 완료 — 이제 공용 PC 터미널에서 s2_pallet_replay.py 를 실행하세요.');
})();

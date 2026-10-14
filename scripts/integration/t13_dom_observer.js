// T13 브라우저 DOM 지연 관측기 (Web PC localhost HMI 콘솔에 붙여 넣는다).
// 입력: 시험용 SortState.pending_question = T13DOM|순번|발행시각|시계오프셋|불확실도
// 출력: ROS 발행 → React DOM 지연 12회와 보수적 상한.
// 근거: docs/interfaces/web_api.md (#54 MC-031), mqtt.md.
(() => {
  const EXPECTED_SAMPLES = 12;
  const marker = /T13DOM\|(\d+)\|(\d+)\|(-?[\d.]+)\|([\d.]+)/;
  const samples = [];
  const seen = new Set();

  if (window.__vossT13Observer) window.__vossT13Observer.disconnect();

  const observer = new MutationObserver(() => {
    const question = document.querySelector('.question');
    const result = question?.textContent?.match(marker);
    if (!result) return;

    const sequence = Number(result[1]);
    if (sequence === 0 || seen.has(sequence)) return;
    seen.add(sequence);

    const publishedOnNodeMs = Number(result[2]);
    const webMinusNodeMs = Number(result[3]);
    const uncertaintyMs = Number(result[4]);
    const displayedOnWebMs = Date.now();
    const measuredMs = displayedOnWebMs - publishedOnNodeMs - webMinusNodeMs;

    samples.push({
      sequence,
      measured_ms: Math.round(measuredMs),
      upper_bound_ms: Math.round(measuredMs + uncertaintyMs),
      uncertainty_ms: uncertaintyMs,
      pass: measuredMs + uncertaintyMs <= 1000,
    });
    console.log(`T13 DOM ${sequence}/${EXPECTED_SAMPLES}: ${measuredMs.toFixed(1)}ms (±${uncertaintyMs.toFixed(1)}ms)`);

    if (samples.length !== EXPECTED_SAMPLES) return;

    observer.disconnect();
    const sorted = [...samples].map(row => row.measured_ms).sort((a, b) => a - b);
    const maxUpperBound = Math.max(...samples.map(row => row.upper_bound_ms));
    const p95 = sorted[Math.ceil(sorted.length * 0.95) - 1];
    const success = samples.every(row => row.pass);
    window.__vossT13Results = samples;

    console.table(samples);
    console.log(
      `T13 측정 완료: 횟수=${samples.length}, p95=${p95}ms, ` +
      `최대 지연 상한=${maxUpperBound}ms, ` +
      `판정=${success ? 'PASS (12/12 <=1초)' : 'FAIL'}`
    );
  });

  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
  });
  window.__vossT13Observer = observer;
  window.__vossT13Results = [];
  console.log('T13 관측 준비 완료. Nodes PC에서 t13_dom_publisher.py를 실행하세요.');
})();

"""T18 정지 송장 OCR 평가: 폴더의 사진 → 라벨 크롭 → PaddleOCR → 퍼지 매칭 → 정답 대조.

정답은 파일명에서 읽는다: `S0701_03.png` → S07-01, `BLUR_S0701_02.png` → S07-01(흐린 송장).
완료 기준(T18): 정지 송장 50장 분류코드 정확도 ≥ 95% (흐린 송장 제외 기준은 NFR-02).
CPU 지연은 참고값이다(완료 수치는 공용 PC GPU 에서만).

  ~/.venvs/voss_ocr/bin/python tools/ocr/eval_static.py --dir <ocr_static> --out <결과.csv>
"""

import argparse
import csv
import re
import statistics
import sys
import time
from pathlib import Path

import cv2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "voss_vision"))
from voss_vision.label_match import candidates_from_config, match_label  # noqa: E402
from voss_vision.label_preprocess import crop_upright, find_label_rect  # noqa: E402

NAME_RE = re.compile(r"^(BLUR_)?S(\d\d)(\d\d)_\d+$")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="이미지별 결과 CSV")
    ap.add_argument("--config", type=Path, default=root / "config" / "voss_config.yaml")
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--clahe", action="store_true")
    ap.add_argument("--save-crops", type=Path, default=None)
    args = ap.parse_args()

    cfg = yaml.safe_load(args.config.read_text())
    cands = candidates_from_config(cfg)
    conf_min = float(cfg["ocr"]["confidence_min"])

    from paddleocr import PaddleOCR  # 무거워서 늦게 불러온다

    # enable_mkldnn=False: paddle 3.3 CPU 의 oneDNN 오류 회피 (GPU 에서는 해당 없음)
    ocr = PaddleOCR(
        lang="korean",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
    )

    rows, lat = [], []
    for p in sorted(args.dir.glob("*.png")):
        g = NAME_RE.match(p.stem)
        if not g:
            continue
        truth = f"S{g[2]}-{g[3]}"
        im = cv2.imread(str(p))
        rect = find_label_rect(im)
        if rect is None:
            rows.append({"file": p.name, "truth": truth, "blur": bool(g[1]), "reason": "NO_LABEL"})
            continue
        crop = crop_upright(im, rect, scale=args.scale, clahe=args.clahe)
        if args.save_crops:
            args.save_crops.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(args.save_crops / p.name), crop)
        t0 = time.perf_counter()
        r = ocr.predict(crop)[0]
        lat.append(time.perf_counter() - t0)
        m = match_label(list(zip(r["rec_texts"], map(float, r["rec_scores"]), strict=True)), cands)
        rows.append(
            {
                "file": p.name,
                "truth": truth,
                "blur": bool(g[1]),
                "code": m.code,
                "dong": m.dong,
                "confidence": m.confidence,
                "reason": m.reason,
                "dong_alt": m.dong_alt,
                "correct": m.code == truth,
                "accepted": m.confidence >= conf_min,
                "raw_text": m.raw_text.replace("\n", " | "),
            }
        )

    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["file"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})

    def acc(sel: list[dict]) -> str:
        n = len(sel)
        ok = sum(bool(r.get("correct")) for r in sel)
        return f"{ok}/{n} = {100 * ok / n:.1f}%" if n else "—"

    clear = [r for r in rows if not r["blur"]]
    blur = [r for r in rows if r["blur"]]
    wrong_acc = [r for r in rows if r.get("accepted") and not r.get("correct")]
    low = [r for r in rows if r.get("code") is not None and not r.get("accepted")]
    print(f"분류코드 정확도 전체 {acc(rows)} | 흐린 송장 제외 {acc(clear)} | 흐린 송장 {acc(blur)}")
    print(
        f"자동 확정(신뢰도 ≥ {conf_min}) 중 오답 {len(wrong_acc)}건 | 재확인행(신뢰도 미만) {len(low)}건"
    )
    for r in wrong_acc + low:
        print(
            f"  {r['file']}: {r.get('code')} {r.get('dong')} {r.get('confidence')} {r.get('reason')} [{r.get('raw_text')}]"
        )
    if lat:
        print(
            f"OCR 지연(CPU, 참고) 중앙값 {statistics.median(lat) * 1000:.0f} ms, 최대 {max(lat) * 1000:.0f} ms"
        )
    print(f"저장 {args.out}")


if __name__ == "__main__":
    main()

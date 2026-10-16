# 생성 및 재검증

Archify 공식 3.1.0 commit `f8021f7eee6870a552bbad3373cf6bad32c80f37`의 `archify/bin/archify.mjs`를 사용한다. 이 디렉터리는 Archify renderer patch가 아니라 SVG/PNG 추출 및 통합 뷰어 조립 스크립트다. Weld-Made의 3.0.1 확장 patch는 사용하지 않는다.

프로젝트 루트에서 각 `data/*.json`에 대해 다음을 실행한다(유형은 system/ros2/flow=`architecture`, erd=`erd`).

```sh
node /path/to/archify/archify/bin/archify.mjs finalize architecture docs/architecture/data/01_system.json docs/architecture/01_system.html --repo-root . --quality standard --json
node /path/to/archify/archify/bin/archify.mjs finalize architecture docs/architecture/data/02_ros2.json docs/architecture/02_ros2.html --repo-root . --quality standard --json
node /path/to/archify/archify/bin/archify.mjs finalize erd docs/architecture/data/03_erd.json docs/architecture/03_erd.html --repo-root . --quality standard --json
node /path/to/archify/archify/bin/archify.mjs finalize architecture docs/architecture/data/04_flow.json docs/architecture/04_flow.html --repo-root . --quality standard --json
```

이후 `python3 docs/architecture/renderer-extension/export_assets.py`(BeautifulSoup4, Pillow, Chrome)와 `python3 docs/architecture/renderer-extension/build_viewer.py`를 실행한다. SVG는 Archify HTML의 실제 inline SVG 및 스타일에서 생성한다. PNG는 standalone SVG의 Chrome 스크린샷이다. 이 재생성 방법은 Viewer의 네이티브 Export와는 다르다. 동일 HTML에 다른 JSON으로 재검증할 때는 Archify의 provenance 규칙에 따라 이전 증빙을 별도 보관하거나 새 `--out-dir`을 사용한다.

## VOSS UI/순서도 확장 (Archify 3.1.0 `f8021f7` 기준)

`archify-voss-ui-shapes.patch`는 다음 파일을 수정한다: `archify/assets/template.html`(첫 실행 Live, Still/Live 선택 저장), `archify/schemas/architecture.schema.json`(Flow `shape`), `archify/renderers/architecture/render-architecture.mjs`(터미네이터·마름모·직사각형·평행사변형·지연형·원통). System/ROS는 도형 속성을 쓰지 않는다. 기준 원본의 default Still 때문에 Live 선 흐름이 보이지 않았고, Flow 기본 사각형은 판단·대기·기록 단계를 구분하지 못했다.

깨끗한 Archify 3.1.0 체크아웃 루트에서 `git apply /path/to/docs/architecture/renderer-extension/archify-voss-ui-shapes.patch`를 실행한 뒤 `node archify/scripts/generate-validators.mjs`로 스키마 validator를 재생성한다. 이후 이 README 상단의 `finalize` 명령을 실행한다. 패치와 도면 JSON이 재생성의 원본이다. 운영체제 `prefers-reduced-motion: reduce`는 계속 우선한다. Live/Still 전환은 Archify 툴바의 동적/정적 버튼을 사용한다.

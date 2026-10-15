import sys
from pathlib import Path

# box_overlay 는 스크립트라 패키지가 아니다 — 같은 폴더를 import 경로에
sys.path.insert(0, str(Path(__file__).resolve().parent))

"""Generate a static registration inventory from ROS Python AST; no runtime claim."""
from pathlib import Path
import ast
R=Path(__file__).resolve().parents[3]
roots=R/'src'
rows=[]
ops={'create_publisher':'Publisher','create_subscription':'Subscriber','create_service':'Service server','create_client':'Service client','ActionServer':'Action server','ActionClient':'Action client'}
for path in sorted(roots.glob('voss_*/voss_*/*.py')):
    tree=ast.parse(path.read_text(),filename=str(path))
    constants={}
    for n in tree.body:
        if isinstance(n,(ast.Assign,ast.AnnAssign)):
            targets=n.targets if isinstance(n,ast.Assign) else [n.target]
            try:v=ast.literal_eval(n.value)
            except (ValueError,TypeError,AttributeError):continue
            if isinstance(v,str):
                for t in targets:
                    if isinstance(t,ast.Name):constants[t.id]=v
    for n in ast.walk(tree):
        if not isinstance(n,ast.Call):continue
        name=n.func.attr if isinstance(n.func,ast.Attribute) else n.func.id if isinstance(n.func,ast.Name) else ''
        if name not in ops:continue
        idx=1 if name in ('ActionServer','ActionClient') else 0
        if len(n.args)<idx+2:continue
        typ=ast.unparse(n.args[idx]);v=n.args[idx+1]
        if isinstance(v,ast.Constant) and isinstance(v.value,str):topic=v.value;resolved=True
        elif isinstance(v,ast.Name) and v.id in constants:topic=constants[v.id];resolved=True
        else:topic=ast.unparse(v);resolved=False
        stage='진단/대체' if path.stem in ('fake_box','fake_gripper','emu_rot','sim_check','camera_preview','usb_camera_preview') else '운전 코드'
        if typ == 'BoxMotion': stage = '조건부/부분 구현'
        rows.append((path.relative_to(R).as_posix(),n.lineno,stage,ops[name],topic,typ,resolved))
lines=['# ROS 2 정적 등록 전체 목록','','`src/voss_*`의 Python AST에서 `create_publisher`, `create_subscription`, `create_service`, `create_client`, `ActionServer`, `ActionClient` 호출을 추출했다. 이 표는 코드 등록 표현식이며 실제 런타임 graph가 아니다. 동적 토픽명, 조건부 생성, 외부 드라이버의 실제 서버는 미확인으로 남긴다. `진단/대체`는 기본 운전 경로로 가정하지 않는다.','','| 파일:줄 | 범위 | 등록 | 이름/표현식 | 타입 표현식 | 해석 |','|---|---|---|---|---|---|']
for path,line,stage,kind,topic,typ,resolved in rows:
    lines.append(f'| `{path}:{line}` | {stage} | {kind} | `{topic.replace("|","\\|")}` | `{typ.replace("|","\\|")}` | {"리터럴/상수" if resolved else "동적·확인 필요"} |')
lines+=['',f'총 {len(rows)}개 등록 호출. 조건부 분기와 실행 인자의 실제 값은 이 표만으로 확정할 수 없다. 표준 드라이버 패키지의 내부 등록은 저장소에 없으므로 제외한다.','']
(R/'docs/architecture/INTERFACES.md').write_text('\n'.join(lines))
print(len(rows),'registrations')

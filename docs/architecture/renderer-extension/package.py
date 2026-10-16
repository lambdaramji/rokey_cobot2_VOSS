"""Write a self-excluding SHA-256 manifest and a verified ZIP of architecture/."""
from pathlib import Path
import hashlib,json,zipfile,tempfile
R=Path(__file__).resolve().parent.parent
OUT=R.parent/'VOSS-architecture.zip'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=sorted(p for p in R.rglob('*') if p.is_file() and p.name!='MANIFEST.json' and '__pycache__' not in p.parts)
manifest={'schema_version':1,'root':'architecture/','note':'MANIFEST.json excludes itself to avoid a recursive hash','files':[{'path':p.relative_to(R).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]}
(R/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(OUT,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in [*files,R/'MANIFEST.json']:z.write(p,Path('architecture')/p.relative_to(R))
with tempfile.TemporaryDirectory() as d:
 with zipfile.ZipFile(OUT) as z:
  assert z.testzip() is None
  z.extractall(d)
  for rec in manifest['files']:
   p=Path(d)/'architecture'/rec['path'];assert p.stat().st_size==rec['bytes'] and sha(p)==rec['sha256']
  assert (Path(d)/'architecture/MANIFEST.json').read_bytes()==(R/'MANIFEST.json').read_bytes()
print(OUT,OUT.stat().st_size,'bytes;',len(files),'hashed files; ZIP roundtrip pass')

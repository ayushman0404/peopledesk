import sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str((Path(__file__).resolve().parents[1] / "PeopleDesk")))
import app
data=Path(tempfile.mkdtemp(prefix="pd-v2-qa-"))
server=app.runserver(data/"demo.db",True,0)
print(server.app.origin,flush=True)
server.serve_forever()

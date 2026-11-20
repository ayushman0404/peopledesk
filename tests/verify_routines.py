import sys,tempfile,threading,concurrent.futures
from pathlib import Path
from contextlib import closing
from datetime import datetime
sys.path.insert(0,str((Path(__file__).resolve().parents[1] / "PeopleDesk")))
import app,routines,company,copilot
from records import *
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp)/"routines.db";application=app.App(p,True,"http://127.0.0.1:0")
 with closing(connect(p)) as db,db:
  u=company.enrich(db,person(db,"E005"))
  r=routines.create(db,u,{"owner":"E002","title":"Daily launch review","detail":"Check blockers","date":"2026-11-20","time":"09:00"})["id"]
 with concurrent.futures.ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:routines.tick(p,datetime(2026,11,20,10)),range(2)))
 with closing(connect(p)) as db:
  runs=rows(db,"SELECT * FROM routine_runs")
  assert len(runs)==1
  assert one(db,"SELECT next_date FROM routines WHERE id=?",(r,))["next_date"]=="2026-11-23"
 routines.tick(p,datetime(2026,11,22,12))
 with closing(connect(p)) as db:assert len(rows(db,"SELECT * FROM routine_runs"))==1
 routines.tick(p,datetime(2026,11,25,12))
 with closing(connect(p)) as db,db:
  assert len(rows(db,"SELECT * FROM routine_runs"))==2
  db.execute("UPDATE profiles SET active=0 WHERE person='E005'")
 routines.tick(p,datetime(2026,11,26,12))
 with closing(connect(p)) as db:
  assert one(db,"SELECT state FROM routines WHERE id=?",(r,))["state"]=="Paused"
  assert len(rows(db,"SELECT * FROM routine_runs"))==2
 print("PASS concurrent routine deduplication, weekday schedule, single catch-up and deactivation pause")
 with closing(connect(p)) as db:
  u=company.enrich(db,person(db,"E001"))
  out=copilot.respond(db,u,"Schedule a Zoom meeting with Karan tomorrow at 3 pm")
  assert out["plan"]["steps"][0]["time"]=="15:00"
  revised=copilot.respond(db,u,"Move it to 4 pm")
  assert revised["plan"]["steps"][0]["time"]=="16:00"
  assert revised["plan"]["id"]==out["plan"]["id"]
 print("PASS natural meeting request and conversational time revision")

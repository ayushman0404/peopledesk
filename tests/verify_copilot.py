import os
import sys,tempfile,threading,json,concurrent.futures
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str((Path(__file__).resolve().parents[1] / "PeopleDesk")))
import app,copilot,assistant_hr
from verify import Browser
from records import *
with tempfile.TemporaryDirectory() as temp:
 server=app.runserver(Path(temp)/"test.db",True,0)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 a=Browser(server.app.origin);e=Browser(server.app.origin);m=Browser(server.app.origin)
 try:
  for b,role in ((a,"hr"),(e,"employee"),(m,"manager")):b.call("login",{"demo":role})
  assert "Hi " in a.call("assistant-talk",{"q":"Hello"})["answer"]
  out=a.call("assistant-talk",{"q":"Assign Karan to review the launch checklist tomorrow"})
  p=out["plan"];assert p["steps"][0]["person"]=="Karan" and p["steps"][0]["date"]==day(1)
  e.call("assistant-run",{"id":p["id"],"version":p["version"]},expect=403)
  changed=a.call("assistant-talk",{"q":"Make it Friday"})["plan"]
  assert changed["version"]==2 and changed["id"]==p["id"]
  a.call("assistant-run",{"id":p["id"],"version":1},expect=400)
  with concurrent.futures.ThreadPoolExecutor(2) as pool:
   results=list(pool.map(lambda _:a.call("assistant-run",{"id":changed["id"],"version":2}),range(2)))
  assert results[0]["receipts"][0]["id"]==results[1]["receipts"][0]["id"]
  tid=results[0]["receipts"][0]["id"]
  assert sum(t["id"]==tid for t in e.call("state")["tasks"])==1
  assert all("plan_id" not in t["body"] for t in e.call("assistant-history",{})["turns"])
  print("PASS conversation, date revision, cross-user denial, stale plan protection and concurrent execution deduplication",flush=True)
  # Atomic rollback when a later event collides. No earlier assignment survives.
  source=a.call("assistant-talk",{"q":"Assign Karan to make atomic test tomorrow"})["plan"]
  steps=[{"kind":"assign","person":"Karan","title":"Rollback fixture","date":day(1)},{"kind":"focus","title":"Focus one","date":day(2),"time":"11:00"},{"kind":"focus","title":"Focus collision","date":day(2),"time":"11:00"}]
  saved=a.call("assistant-edit",{"id":source["id"],"version":1,"steps":steps})["plan"]
  a.call("assistant-run",{"id":saved["id"],"version":saved["version"]},expect=400)
  assert not any(t["title"]=="Rollback fixture" for t in a.call("state")["tasks"])
  a.call("assistant-cancel",{"id":saved["id"]})
  a.call("assistant-run",{"id":saved["id"],"version":saved["version"]},expect=400)
  # An employee's proposed assignment remains an invitation; the assistant cannot elevate it.
  p=e.call("assistant-talk",{"q":"Assign Nora to review the rollout tomorrow"})["plan"]
  done=e.call("assistant-talk",{"q":"do it"})
  assert "invitation" in done["receipts"][0]["label"]
  t=next(t for t in e.call("state")["tasks"] if t["id"]==done["receipts"][0]["id"])
  assert t["accepted"]==0
  print("PASS all-or-nothing rollback, cancellation and collaboration consent",flush=True)
  # Multi-tool execution: focus, email draft, meeting request. None dispatches externally.
  p=a.call("assistant-talk",{"q":"Assign Karan to seed review tomorrow"})["plan"]
  steps=[{"kind":"focus","title":"Prepare the launch","date":day(3),"time":"10:00"},{"kind":"email","person":"Karan","title":"Launch update","detail":"Hi Karan, please share your launch update."},{"kind":"meeting","person":"Karan","title":"Zoom launch check-in","date":day(3),"time":"13:00"}]
  p=a.call("assistant-edit",{"id":p["id"],"version":p["version"],"steps":steps})["plan"]
  done=a.call("assistant-run",{"id":p["id"],"version":p["version"]})
  assert len(done["receipts"])==3
  state=a.call("state")
  requests=[r for r in state["requests"] if r["id"] in {x["id"] for x in done["receipts"]}]
  assert len(requests)==2 and all(r["status"]=="Pending" and not r["actions"] for r in requests)
  brief=m.call("assistant-talk",{"q":"Give me a workload brief"})
  visible={t["id"] for t in m.call("state")["tasks"]}
  assert all(s["id"] in visible for s in brief["sources"])
  s=a.call("assistant-talk",{"q":"Fire Karan"})
  assert s["action"]["type"]=="case"
  print("PASS multi-action results, HR approval boundary, scoped workload brief and consequential-decision handoff",flush=True)
  multi=a.call("assistant-talk",{"q":"Assign Karan to review release notes tomorrow and schedule a Zoom meeting with Nora tomorrow at 3 pm"})
  assert [s["kind"] for s in multi["plan"]["steps"]]==["assign","meeting"]
  focus=a.call("assistant-talk",{"q":"Block focus time tomorrow at 11 am"})
  assert focus["plan"]["steps"][0]["kind"]=="focus"
  print("PASS natural multi-action request and focus-time planning",flush=True)
  if os.environ.get("PEOPLEDESK_TEST_MODEL") == "1":
   # Exercise the real local LLM's structured action generation.
   out=a.call("assistant-talk",{"q":"Draft an email to Karan asking him to share the launch update."})
   assert out.get("plan") and out["plan"]["steps"][0]["kind"]=="email",out
   step=out["plan"]["steps"][0];assert step["detail"] and step["person"]
   print("PASS real local Qwen produces an actionable email plan:",step["title"],flush=True)
  else:
   print("SKIP real local-model plan; set PEOPLEDESK_TEST_MODEL=1 to run.", flush=True)
 finally:server.shutdown();server.server_close()

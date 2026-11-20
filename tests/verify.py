"""End-to-end request tests with independent employee and HR browser sessions."""
import os
import concurrent.futures
import contextlib
import csv
import http.cookiejar
import io
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import urllib.error,urllib.request
from unittest.mock import patch
import zipfile

BASE=(Path(__file__).resolve().parents[1] / "PeopleDesk")
sys.path.insert(0,str(BASE))
import app, providers, records,service
from records import day,today

class Browser:
    def __init__(self,origin):
        self.origin=origin
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(self,op,d=None,path=None,expect=200,token=None):
        if d is not None: d=dict(d,token=token or secrets.token_hex(12))
        req=urllib.request.Request(self.origin+(path or "/api/"+op),data=None if d is None else json.dumps(d).encode(),headers={"Content-Type":"application/json","Origin":self.origin})
        try: reply=self.opener.open(req,timeout=180)
        except urllib.error.HTTPError as err: reply=err
        data=reply.read();status=reply.status
        assert status==expect,(op,status,data[:600])
        return json.loads(data) if reply.headers.get_content_type()=="application/json" else data
def run():
    with tempfile.TemporaryDirectory() as temp:
        dbfile=Path(temp)/"demo.db";server=app.runserver(dbfile,True,0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        origin=server.app.origin;hr=Browser(origin);emp=Browser(origin)
        try:
            assert b"PeopleDesk" in hr.call(None,path="/")
            assert hr.call("info")["demo"]
            hr.call("login",{"demo":"hr"});emp.call("login",{"demo":"employee"})
            s=hr.call("state");es=emp.call("state")
            assert len(s["people"])==32 and len(s["policies"])==10
            assert all("balance" not in p for p in es["people"])
            assert es["handoffs"]==[] and es["flows"]==[]
            q="How many days of leave are remaining of Karan?"
            result=hr.call("chat",{"q":q});assert "18 working days" in result["answer"] and len(result["sources"])==2
            assert not emp.call("chat",{"q":"How much leave balance does Maya have?"})["sources"]
            assert "30 days" in emp.call("chat",{"q":"What is the reimbursement policy?"})["sources"][0]["text"]
            case=emp.call("chat",{"q":"I want to report harassment"})["action"];assert case["type"]=="case"
            req=next(r for r in s["requests"] if r["kind"]=="Leave")
            emp.call("review",{"id":req["id"],"decision":"Approved"},expect=403)
            token=secrets.token_hex(10)
            data={"id":req["id"],"decision":"Approved","note":"Coverage checked."}
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(hr.call,"review",data,token=token) for _ in range(2)]
                for f in futures: assert f.result()=={}
            after=hr.call("chat",{"q":q});assert "17 working days" in after["answer"] and len(after["sources"])==3
            hr.call("review",data,expect=400)
            emp.call("request",{"kind":"Leave","subject":"E004","start":day(8),"end":day(8)},expect=403)
            print("PASS balances, authoritative sources, distinct roles, duplicate-safe concurrent approval",flush=True)
            d=day(2)
            meet=emp.call("chat",{"q":"Schedule a Zoom meeting with Nora on "+d+" at 3 pm"})["action"]
            assert meet["starts"]==d+"T15:00" and "E003" in meet["people"] and meet["zoom"]
            mid=emp.call("request",{**meet,"kind":"Meeting","title":"Project handover","minutes":30})["id"]
            hr.call("review",{"id":mid,"decision":"Approved"});assert b"BEGIN:VEVENT" in emp.call(None,path="/export/meeting/"+mid)
            hr.call("request",{**meet,"kind":"Meeting","title":"Conflict","minutes":30},expect=400)
            emp.call("work-block",{"title":"Checklist prep","starts":d+"T13:00","minutes":30})
            mail=next(r for r in s["requests"] if r["kind"]=="Email")
            hr.call("revise-email",{"id":mail["id"],"to":"iris@aster.example","title":"Confirmed welcome","message":"Hi Iris, your welcome pack is ready."})
            hr.call("review",{"id":mail["id"],"decision":"Approved","revision":1},expect=400)
            hr.call("review",{"id":mail["id"],"decision":"Approved","revision":2})
            assert b"Confirmed welcome" in hr.call(None,path="/export/email/"+mail["id"])
            hr.call("external",{"id":mail["id"],"channel":"Gmail send"},expect=400)
            print("PASS meeting request, collision check, work block, ICS and reviewed email export",flush=True)
            fid=hr.call("flow",{"kind":"Payroll support","subject":"E002","title":"Missing payslip","begin":day()})["id"]
            note=hr.call("flow-note",{"flow":fid,"note":"Payroll case reference","filename":"case.txt","attachment":"YWJj"})["id"]
            assert hr.call(None,path="/export/document/"+note)==b"abc"
            emp.call(None,path="/export/document/"+note,expect=403)
            task=next(t for t in emp.call("state")["tasks"] if t["owner"]=="E002")
            emp.call("snooze",{"id":task["id"]});assert task["id"] not in emp.call("state")["reminders"]
            emp.call("task-status",{"id":task["id"],"status":"Done"})
            if os.environ.get("PEOPLEDESK_TEST_MODEL") == "1":
                hid=hr.call("handoff",{"notes":"Karan will send the setup checklist on Friday."})["id"]
                h=next(h for h in hr.call("state")["handoffs"] if h["id"]==hid)
                item=h["items"][0];assert item["kind"]=="Action" and item["owner"]=="Karan"
                assignment={"handoff":hid,"item":item["id"],"owner":"E002","helper":"E005","due":day(3)}
                a=hr.call("promote",assignment)["id"];assert hr.call("promote",assignment)["id"]==a
                hr.call("review",{"id":a,"decision":"Approved"})
                assert any(hid in t["source"] and t["helper"]=="E005" for t in emp.call("state")["tasks"])
                mail=hr.call("draft",{"to":"karan@aster.example","brief":"Invite Karan to review the onboarding checklist. Ask him for a convenient time."})
                assert len(mail["message"])>25 and mail["subject"]
                print("PASS Qwen handoff, assignment with collaborator, live model email draft, workflow evidence and reminders",flush=True)
                print("Live draft:",mail["subject"],flush=True)
            else:
                print("SKIP local-model handoff/email; set PEOPLEDESK_TEST_MODEL=1 to run.", flush=True)
        finally:server.shutdown();server.server_close()

        company=Path(temp)/"company.db"; server=app.runserver(company,False,0)
        with contextlib.closing(records.connect(company)) as db,db:
            db.execute("INSERT INTO people VALUES('HR','Reviewer','hr@example.test','People','HR','hr',NULL,?,'London',?)",(day(),records.password("example-password-42")))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        owner=Browser(server.app.origin)
        try:
            owner.call("login",{"demo":"hr"},expect=400)
            owner.call("login",{"email":"hr@example.test","password":"example-password-42"})
            user=owner.call("add-person",{"name":"Karan Bose","email":"k@example.test","team":"Finance","title":"Analyst","manager":"HR","start":day(),"balance":12,"location":"London","password":"example-employee-42"})["id"]
            realEmp=Browser(server.app.origin);realEmp.call("login",{"email":"k@example.test","password":"example-employee-42"})
            assert "12 working days" in realEmp.call("chat",{"q":"How many days of leave do I have remaining?"})["answer"]
            owner.call("policy",{"title":"Device policy","keywords":"laptop equipment","body":"Request a laptop from IT.","version":"1"})
            assert "Request a laptop" in realEmp.call("chat",{"q":"What is the laptop policy?"})["sources"][0]["text"]
            rid=owner.call("request",{"kind":"Email","subject":user,"title":"Welcome","to":"k@example.test","message":"Welcome to the team."})["id"]
            owner.call("review",{"id":rid,"decision":"Approved"})
            with contextlib.closing(records.connect(company)) as db,db:
                protected=providers.protect(b'{"refresh_token":"fixture","email":"hr@example.test"}');assert providers.protect(protected,True).startswith(b'{')
                db.execute("INSERT INTO secrets VALUES('google:HR',?)",(protected,))
            with patch.object(providers,"publish",return_value=("fixture-draft","Created in Gmail drafts")) as stub:
                owner.call("external",{"id":rid,"channel":"Gmail draft"})
                owner.call("external",{"id":rid,"channel":"Gmail draft"},expect=400)
                assert stub.call_count==1
            with patch.object(providers,"publish",side_effect=TimeoutError):
                owner.call("external",{"id":rid,"channel":"Gmail send"},expect=400)
            assert any(a["status"]=="Verify with provider" for a in owner.call("state")["requests"][0]["actions"])
            print("PASS clean company setup, password sign-in, editable policies, provider dispatch with test double and uncertain outcome handling",flush=True)
        finally:server.shutdown();server.server_close()
def export_demo():
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp)/"demo.db";records.init(p,True)
        with contextlib.closing(records.connect(p)) as db, zipfile.ZipFile(BASE/"Aster-Works-demo-data.zip","w",zipfile.ZIP_DEFLATED) as z:
            for table in ("people","ledger","policies","requests","tasks","flows","events"):
                data=records.rows(db,"SELECT * FROM "+table)
                cols=[x for x in data[0] if x!="hash"];out=io.StringIO(newline="")
                writer=csv.DictWriter(out,fieldnames=cols,extrasaction="ignore");writer.writeheader();writer.writerows(data)
                z.writestr(table+".csv",out.getvalue().encode("utf-8-sig"))
            z.writestr("README.txt","Fictional company records for the PeopleDesk demo. Join people.id to person, subject, owner, helper, creator or manager. Leave balance equals the sum of ledger.days grouped by person. requests.body and events.people are JSON. No personal source dataset was used.")
if __name__=="__main__":
    run()
    # Demo records are generated by the application; no archive is written by tests.

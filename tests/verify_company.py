"""Company enrollment, access isolation and provider contracts; no live accounts."""
import contextlib,base64,json,tempfile,threading,sys,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str((Path(__file__).resolve().parents[1] / "PeopleDesk")))
from verify import Browser
import app,company,cloud,providers,records
from records import *
from google.oauth2 import id_token

def run():
 with tempfile.TemporaryDirectory() as tmp:
  path=Path(tmp)/"company.db"
  server=app.runserver(path,False,0)
  threading.Thread(target=server.serve_forever,daemon=True).start()
  root=Browser(server.app.origin);employee=Browser(server.app.origin);colleague=Browser(server.app.origin);manager=Browser(server.app.origin)
  try:
   data=dict(company="Northstar QA",name="Founder Test",email="founder@example.test",password="Very secure test password!")
   root.call("workspace-setup",dict(data,setup_token="wrong"),expect=403)
   root.call("workspace-setup",dict(data,setup_token=server.app.setup_token))
   owner=root.call("state")["user"]["id"]
   root.call("workspace-setup",dict(data,setup_token="wrong"),expect=403)
   root.call("invite",dict(email="employee@example.test",team="Engineering",title="Engineer",access="employee",manager=owner))
   employee.call("register",dict(name="Employee Test",email="employee@example.test",password="Very secure employee password!",team="Engineering",title="Engineer",access="owner"))
   employee.call("login",dict(email="employee@example.test",password="Very secure employee password!"),expect=403)
   pending=root.call("state")["registrations"][0]
   assert "hash" not in pending
   root.call("membership",dict(id=pending["id"],decision="Approved",access="employee",manager=owner))
   employee.call("login",dict(email="employee@example.test",password="Very secure employee password!"))
   emp=employee.call("state")["user"]["id"]
   assert employee.call("state")["user"]["access"]=="employee"
   employee.call("leave-adjust",dict(id=emp,days=24,reason="Opening balance"),expect=403)
   for _ in range(2):root.call("leave-adjust",dict(id=emp,days=24,reason="Opening balance"),token="opening-entitlement")
   assert sum(l["days"] for l in employee.call("state")["ledger"])==24
   root.call("leave-adjust",dict(id=emp,days=-25,reason="Invalid correction"),expect=400)
   employee.call("member-access",dict(id=emp,access="owner"),expect=403)
   employee.call("provider-config",{"GOOGLE_CLIENT_SECRET":"unwanted"},expect=403)
   inv=root.call("invite",dict(email="manager@example.test",team="Engineering",title="VP",access="manager",manager=owner))["invitation"]
   manager.call("register",dict(name="Manager Test",email="wrong@example.test",password="Strong manager password!",invitation=inv),expect=400)
   manager.call("register",dict(name="Manager Test",email="manager@example.test",password="Strong manager password!",invitation=inv))
   manager.call("register",dict(name="Manager Test",email="manager@example.test",password="Strong manager password!",invitation=inv),expect=400)
   manager.call("login",dict(email="manager@example.test",password="Strong manager password!"))
   mid=manager.call("state")["user"]["id"]
   inv2=root.call("invite",dict(email="colleague@example.test",team="Sales",title="Associate",access="employee",manager=owner))["invitation"]
   colleague.call("register",dict(name="Colleague Test",email="colleague@example.test",password="Strong colleague password!",invitation=inv2))
   colleague.call("login",dict(email="colleague@example.test",password="Strong colleague password!"))
   cid=colleague.call("state")["user"]["id"]
   assert not employee.call("state")["registrations"]
   root.call("member-access",dict(id=owner,access="employee",active="0",team="Leadership",title="Founder"),expect=400)
   print("PASS web company setup, pending enrollment, one-use invitations and role escalation denial",flush=True)
   assignment=manager.call("assign",dict(owner=emp,title="Prepare rollout",due=day(1),project="Launch"))["id"]
   assert next(t for t in employee.call("state")["tasks"] if t["id"]==assignment)["accepted"]==1
   assert not any(t["id"]==assignment for t in colleague.call("state")["tasks"])
   colleague.call("task-progress",dict(id=assignment,status="Done"),expect=403)
   proposal=employee.call("assign",dict(owner=cid,title="Coordinate launch",due=day(1)))["id"]
   employee.call("task-progress",dict(id=proposal,status="Done"),expect=400)
   employee.call("accept-task",dict(id=proposal),expect=403)
   colleague.call("accept-task",dict(id=proposal))
   colleague.call("task-progress",dict(id=proposal,status="In progress"))
   fid=employee.call("share-file",dict(filename="private.txt",attachment=base64.b64encode(b"private fixture").decode(),audience="private"))["id"]
   root.call(None,path="/export/shared/"+fid,expect=403)
   assert employee.call(None,path="/export/shared/"+fid)==b"private fixture"
   teamfile=employee.call("share-file",dict(filename="team.txt",attachment=base64.b64encode(b"team fixture").decode(),audience="team:Engineering"))["id"]
   assert manager.call(None,path="/export/shared/"+teamfile)==b"team fixture"
   colleague.call(None,path="/export/shared/"+teamfile,expect=403)
   assert not any(f["id"]==fid for f in root.call("state")["files"])
   print("PASS management scope, collaboration consent and file access controls",flush=True)
   root.call("provider-config",{"GOOGLE_CLIENT_ID":"fixture-client","GOOGLE_CLIENT_SECRET":"fixture-secret"})
   with contextlib.closing(connect(path)) as db,db:
    db.execute("INSERT INTO secrets VALUES(?,?)",("google:"+emp,providers.protect(json.dumps({"refresh_token":"fixture-refresh","email":"employee@example.test"}).encode())))
   calls=[]
   def remote(url,method="GET",data=None,token=None,**kwargs):
    calls.append((url,method,data,token))
    if "oauth2.googleapis.com/token" in url:return {"access_token":"fixture-bearer"}
    assert token=="fixture-bearer"
    if "calendar/v3" in url:return {"items":[{"id":"private-event","summary":"Private doctor visit","start":{"dateTime":day(1)+"T10:30:00+05:30"},"end":{"dateTime":day(1)+"T11:00:00+05:30"},"htmlLink":"https://calendar.google.com/"}]}
    if "drive/v3" in url:return {"files":[{"id":"f1","name":"Private budget","webViewLink":"https://drive.google.com/file/f1"}]}
    if "tasks/v1" in url:
     if method in ("POST","PATCH"):return {"id":"remote-task"}
     return {"items":[{"id":"t1","title":"Personal follow up","status":"needsAction"}]}
    if "/messages/send" in url:return {"id":"message-out"}
    if "/messages/m1" in url:return {"id":"m1","payload":{"headers":[{"name":"Subject","value":"Private inbox item"}]}}
    if "/messages?" in url:return {"messages":[{"id":"m1"}]}
    raise AssertionError(url)
   with patch.object(providers,"remote",side_effect=remote):
    employee.call("cloud-refresh",{})
    state=employee.call("state")
    assert len(state["cloud"])==4
    e=next(e for e in state["events"] if e.get("remote"))
    assert e["starts"]==day(1)+"T05:00"
    assert root.call("state")["cloud"]==[]
    assert all(e["title"]!="Private doctor visit" for e in root.call("state")["events"])
    employee.call("cloud-task",dict(id=assignment))
    employee.call("task-progress",dict(id=assignment,status="Done"))
    employee.call("cloud-task",dict(id=assignment))
    assert len([c for c in calls if "tasks/v1" in c[0] and c[1]=="POST"])==1
    assert len([c for c in calls if "tasks/v1" in c[0] and c[1]=="PATCH"])==1
    assert [c for c in calls if c[1]=="PATCH"][-1][2]["status"]=="completed"
    employee.call("cloud-digest",{})
    employee.call("cloud-digest",{},expect=400)
   def fail_files(url,*a,**kw):
    if "drive/v3" in url:raise TimeoutError
    return remote(url,*a,**kw)
   with patch.object(providers,"remote",side_effect=fail_files):
    out=employee.call("cloud-refresh",{})
    assert "previous results are retained" in out["message"]
   assert any(c["body"].get("name")=="Private budget" for c in employee.call("state")["cloud"])
   with contextlib.closing(connect(path)) as db,db:
    db.execute("UPDATE cloud_jobs SET state='In progress' WHERE person=? AND provider='Google Tasks'",(emp,))
   reopened=app.App(path,False,server.app.origin)
   with contextlib.closing(connect(path)) as db:
    assert one(db,"SELECT state FROM cloud_jobs WHERE person=? AND provider='Google Tasks'",(emp,))["state"]=="Verify with provider"
   with patch.object(providers,"remote",side_effect=remote):
    employee.call("cloud-task",dict(id=assignment),expect=400)
   print("PASS per-person provider isolation, UTC calendar import, update without duplicates and interrupted-sync recovery (provider doubles)",flush=True)
   # Actual signature/audience/expiry/issuer verification with a locally generated RSA key.
   from cryptography.hazmat.primitives.asymmetric import rsa
   from cryptography.hazmat.primitives import serialization
   from google.auth import crypt,jwt
   private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
   pem=private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
   public=private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
   signer=crypt.RSASigner.from_string(pem,key_id="fixture")
   claims={"iss":"https://accounts.google.com","aud":"fixture-client","sub":"verified-sub","iat":int(time.time())-10,"exp":int(time.time())+3600}
   with patch.object(id_token,"_fetch_certs",return_value={"fixture":public.decode()}):
    signed=jwt.encode(signer,claims)
    assert id_token.verify_oauth2_token(signed,None,"fixture-client")["sub"]=="verified-sub"
    for changed in ({"aud":"attacker"},{"iss":"https://attacker.example"},{"exp":int(time.time())-1000}):
     try:id_token.verify_oauth2_token(jwt.encode(signer,dict(claims,**changed)),None,"fixture-client")
     except Exception:pass
     else:raise AssertionError("Accepted invalid token")
    forged=signed[:-12]+b"aaaaaaaaaaaa"
    try:id_token.verify_oauth2_token(forged,None,"fixture-client")
    except Exception:pass
    else:raise AssertionError("Accepted altered signature")
   # OAuth browser state cookie + nonce, single-use state and existing-email sign in.
   fresh=Browser(server.app.origin)
   url=fresh.call("google-login",{})["url"]
   import urllib.parse
   qs=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
   oauth=server.app.oauth[qs["state"][0]]
   query="/oauth/account?state="+qs["state"][0]+"&code=fixture-code"
   with patch.object(providers,"remote",return_value={"id_token":"fixture-id"}),patch.object(id_token,"verify_oauth2_token",return_value=dict(claims,nonce=oauth["nonce"],email_verified=True,email="employee@example.test")) as verifier:
    # A different browser cannot consume another browser's OAuth state.
    # Avoid consuming the legitimate state: use independent new session for this negative case.
    url2=Browser(server.app.origin).call("google-login",{})["url"]
    bad=urllib.parse.parse_qs(urllib.parse.urlsplit(url2).query)["state"][0]
    fresh.call(None,path="/oauth/account?state="+bad+"&code=fixture",expect=400)
    fresh.call(None,path=query) # urllib follows the successful redirect.
    assert fresh.call("state")["user"]["id"]==emp
    fresh.call(None,path=query,expect=400)
    assert verifier.call_count==1
   nonceBrowser=Browser(server.app.origin)
   nonceUrl=nonceBrowser.call("google-login",{})["url"]
   nonceState=urllib.parse.parse_qs(urllib.parse.urlsplit(nonceUrl).query)["state"][0]
   with patch.object(providers,"remote",return_value={"id_token":"fixture-id"}),patch.object(id_token,"verify_oauth2_token",return_value=dict(claims,nonce="wrong",email_verified=True,email="employee@example.test")):
    nonceBrowser.call(None,path="/oauth/account?state="+nonceState+"&code=fixture",expect=400)
   assert not nonceBrowser.call("info")["signed"]
   root.call("member-access",dict(id=emp,access="employee",active="0",team="Engineering",title="Engineer",manager=mid))
   employee.call("state",expect=403)
   fresh.call("state",expect=403)
   employee.call("login",dict(email="employee@example.test",password="Very secure employee password!"),expect=403)
   print("PASS real JWT verification, OAuth browser binding, nonce, replay protection and deactivation",flush=True)
  finally:server.shutdown();server.server_close()
if __name__=="__main__":run()

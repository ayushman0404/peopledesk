const {spawn}=require("child_process");
const path=require("path"),fs=require("fs");
const {chromium}=require("playwright");
const assert=require("assert");
(async()=>{
 const packaged=process.env.PEOPLEDESK_TEST_EXE;
 let origin,proc;
 if(packaged){
   const net=require('net');
   const port=await new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p))})});
   origin='http://127.0.0.1:'+port;
   const data=fs.mkdtempSync(path.join(require('os').tmpdir(),'peopledesk-package-'));
   proc=spawn(packaged,['--no-browser'],{windowsHide:true,env:{...process.env,PEOPLEDESK_PORT:String(port),PEOPLEDESK_DATA:data},stdio:['ignore','pipe','pipe']});
   const deadline=Date.now()+25000;let up=false;
   while(Date.now()<deadline){try{up=(await fetch(origin+'/api/info')).ok;if(up)break}catch{}await new Promise(r=>setTimeout(r,200))}
   if(!up){proc.kill();throw Error('Packaged service did not start')}
 } else proc=spawn("python",["-u","tests/preview_v2.py"],{windowsHide:true,stdio:["ignore","pipe","pipe"]});
 let stderr="";proc.stderr.on("data",d=>stderr+=d);
 if(!origin)origin=await new Promise((resolve,reject)=>{proc.stdout.once("data",d=>resolve(d.toString().trim()));proc.once("exit",()=>reject(Error(stderr)))});
 console.log(packaged?"Packaged service started":"Source service started",origin);
 let browser,admin;
 try {
 browser=await chromium.launch({headless:true,timeout:18000,args:["--disable-gpu","--no-proxy-server"]});
 const errors=[];
 async function account(role) {
  const context=await browser.newContext({viewport:{width:1440,height:980}});
  const page=await context.newPage();page.setDefaultTimeout(15000);page.on("pageerror",e=>errors.push(e.message));
  await page.goto(origin);
  await page.getByRole("heading",{name:"Operations overview",exact:true}).waitFor();
  if(role!=="hr"){await page.locator("#demo-role").selectOption(role);await page.getByRole("heading",{name:"My day",exact:true}).waitFor();}
  return {page,context};
 }
 admin=await account("hr");const karan=await account("employee"),ravi=await account("manager"),nora=await account("lead");
 async function call(a,op,data){return a.page.evaluate(async({op,data})=>{const r=await fetch("/api/"+op,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...data,token:crypto.randomUUID()})});return {status:r.status,body:await r.json()};},{op,data});}
 await karan.page.getByRole("button",{name:"Tomorrow",exact:true}).click();
 await karan.page.getByRole("button",{name:"Today",exact:true}).click();
 await karan.page.screenshot({path:"tests/Employee-v2.png"});
 console.log("Employee portal rendered");

 await admin.page.getByRole('button',{name:'Assistant',exact:true}).click();
 await admin.page.waitForFunction(()=>Copilot.loaded);
 await admin.page.screenshot({path:'tests/Assistant-home.png'});
 const speak=async(q)=>{
  await admin.page.getByRole('textbox',{name:'Tell PeopleDesk what to do'}).fill(q);
  await admin.page.getByRole('button',{name:'Send to PeopleDesk',exact:true}).click();
  await admin.page.waitForFunction(()=>!Copilot.busy,{},{timeout:150000});
 };
 await speak('Assign Karan to review assistant rollout tomorrow');
 await admin.page.getByRole('button',{name:'Edit details',exact:true}).click();
 await admin.page.getByLabel('Title',{exact:true}).fill('Review assistant rollout with design');
 await admin.page.getByRole('button',{name:'Save plan',exact:true}).click();
 await admin.page.getByRole('dialog').waitFor({state:'hidden'});
 await admin.page.getByRole('button',{name:'Run plan',exact:true}).click();
 await admin.page.locator('.execution-receipt').filter({hasText:'Assigned to Karan'}).waitFor();
 await admin.page.screenshot({path:'tests/Assistant-executed.png'});
 await admin.page.reload();await admin.page.waitForFunction(()=>Copilot.loaded);
 await admin.page.locator('.execution-receipt').filter({hasText:'Assigned to Karan'}).waitFor();
 await admin.page.getByRole('button',{name:'Find anything',exact:true}).click();
 await admin.page.getByLabel('Search people, tasks, meetings, policies and files').fill('Review assistant rollout with design');
 await admin.page.locator('.search-hit').filter({hasText:'Review assistant rollout with design'}).click();
 await admin.page.getByRole('heading',{name:'Review assistant rollout with design',exact:true}).waitFor();
 await admin.page.getByRole('button',{name:'Close',exact:true}).click();
 await admin.page.getByRole('button',{name:'Routines',exact:true}).click();
 await admin.page.getByRole('button',{name:'Create routine',exact:true}).click();
 await admin.page.getByLabel('Task title',{exact:true}).fill('Review daily launch blockers');
 await admin.page.getByRole('button',{name:'Review routine',exact:true}).click();
 await admin.page.getByRole('button',{name:'Run plan',exact:true}).click();
 await admin.page.locator('.execution-receipt').filter({hasText:'Weekday task routine enabled'}).waitFor();
 await admin.page.getByRole('button',{name:'Routines',exact:true}).click();
 await admin.page.getByRole('button',{name:'Pause routine',exact:true}).click();
 await admin.page.getByRole('button',{name:'Resume routine',exact:true}).waitFor();
 console.log('PASS assistant edit/execute/history/search and routine controls');
 await ravi.page.getByRole("button",{name:"Team workspace",exact:true}).click();
 await ravi.page.getByRole("button",{name:"Create assignment",exact:true}).click();
 await ravi.page.getByLabel("Task title").fill("Review launch telemetry");
 await ravi.page.getByLabel("Responsible person").selectOption("E002");
 await ravi.page.getByLabel("Collaborator", {exact:false}).selectOption("E005");
 await ravi.page.getByRole("button",{name:"Create assignment",exact:true}).last().click();
 await ravi.page.getByRole("heading",{name:"Review launch telemetry",exact:true}).waitFor();
 await ravi.page.getByRole("button",{name:"Close",exact:true}).click();
 await karan.page.reload();await karan.page.getByRole("heading",{name:"My day",exact:true}).waitFor();
 await karan.page.getByRole("button",{name:"Tomorrow",exact:true}).click();
 await karan.page.getByRole("button",{name:"Review launch telemetry",exact:false}).click();
 await karan.page.getByRole("button",{name:"In progress",exact:true}).click();
 await karan.page.getByRole("button",{name:"Close",exact:true}).click();
 console.log("Manager assignment and employee progress passed");
 for(const a of [karan,ravi,nora]){
   await a.page.getByRole("button",{name:"Messages",exact:true}).click();
   await a.page.getByLabel("Chat passphrase (16+ characters)").fill("Demo passphrase for private messages 2026!");
   await a.page.getByRole("button",{name:"Unlock private chat",exact:true}).click();
   await a.page.getByRole("button",{name:"New conversation",exact:true}).waitFor({timeout:30000});
 }
 console.log("Three browser identities registered");
 await karan.page.getByRole("button",{name:"New conversation",exact:true}).click();
 await karan.page.getByLabel("Conversation type").selectOption("group");
 await karan.page.getByLabel("Group name").fill("Platform launch");
 await karan.page.getByRole("checkbox",{name:"Ravi Shah",exact:true}).check();
 await karan.page.getByRole("checkbox",{name:"Nora Chen",exact:true}).check();
 await karan.page.getByRole("button",{name:"Start conversation",exact:true}).click();
 await karan.page.getByRole("textbox",{name:"Message",exact:true}).fill("PRIVATE-LAUNCH-8734: Can we review the setup tomorrow?");
 await karan.page.getByRole("button",{name:"Send encrypted message",exact:true}).click();
 await karan.page.locator(".message p").filter({hasText:"PRIVATE-LAUNCH-8734"}).waitFor();
 const rid=await karan.page.evaluate(()=>Messenger.room.id);
 const unauthorized=await call(admin,"messages-read",{room:rid});
 assert.equal(unauthorized.status,403);
 const raw=await call(karan,"messages-read",{room:rid});
 assert(!JSON.stringify(raw).includes("PRIVATE-LAUNCH-8734"));
 const envelope=raw.body.messages[0].envelope;
 assert.equal((await call(karan,"message-send",{room:rid,envelope})).status,200);
 const forged=JSON.parse(JSON.stringify(envelope));forged.payload.sender="E005";
 assert.equal((await call(karan,"message-send",{room:rid,envelope:forged})).status,400);
 const tampered=JSON.parse(JSON.stringify(raw.body.messages[0]));
 tampered.envelope.signature='A'.repeat(86)+'==';
 assert(await karan.page.evaluate(async item=>{try{await Messenger.decode(item,Messenger.room);return false}catch{return true}},tampered));
 await ravi.page.getByRole("button",{name:"Refresh conversations",exact:true}).click();
 await ravi.page.getByRole("button",{name:"Platform launch",exact:false}).click();
 await ravi.page.locator(".message p").filter({hasText:"PRIVATE-LAUNCH-8734"}).waitFor();
 await ravi.page.getByRole("textbox",{name:"Message",exact:true}).fill("Yes, I will join and help Karan with telemetry.");
 await ravi.page.getByRole("button",{name:"Send encrypted message",exact:true}).click();
 await karan.page.getByText("Yes, I will join and help Karan with telemetry.",{exact:true}).waitFor({timeout:10000});
 await karan.page.screenshot({path:"tests/Messages-v2.png"});
 const fresh=await account("employee");
 await fresh.page.getByRole("button",{name:"Messages",exact:true}).click();
 await fresh.page.getByLabel("Chat passphrase (16+ characters)").fill("An incorrect recovery passphrase!");
 await fresh.page.getByRole("button",{name:"Unlock private chat",exact:true}).click();
 await fresh.page.getByText("The chat passphrase did not unlock your keys. Your existing identity has been preserved.",{exact:true}).waitFor();
 await fresh.page.getByLabel("Chat passphrase (16+ characters)").fill("Demo passphrase for private messages 2026!");
 await fresh.page.getByRole("button",{name:"Unlock private chat",exact:true}).click();
 await fresh.page.getByRole("button",{name:"Platform launch",exact:false}).waitFor({timeout:30000});
 await fresh.page.getByRole("button",{name:"Platform launch",exact:false}).click();
 await fresh.page.locator(".message p").filter({hasText:"PRIVATE-LAUNCH-8734"}).waitFor();
 console.log("PASS encrypted group delivery, cross-device recovery, server ciphertext and administrator denial");
 await fresh.page.getByRole("button",{name:"New conversation",exact:true}).click();
 await fresh.page.getByRole("checkbox",{name:"Ravi Shah",exact:true}).check();
 await fresh.page.getByRole("button",{name:"Start conversation",exact:true}).click();
 await fresh.page.locator('.conversation-head h2').filter({hasText:'Ravi Shah'}).waitFor();
 await fresh.page.getByRole("textbox",{name:"Message",exact:true}).fill("Direct conversation check");
 await fresh.page.getByRole("button",{name:"Send encrypted message",exact:true}).click();
 await fresh.page.getByText("Direct conversation check",{exact:true}).waitFor();
 await ravi.page.getByRole("button",{name:"Refresh conversations",exact:true}).click();
 await ravi.page.locator('.conversation-link').filter({hasText:'Karan Mehta'}).click();
 await ravi.page.getByText("Direct conversation check",{exact:true}).waitFor();
 console.log("PASS direct messages, incorrect passphrase recovery, replay handling and tampered signature rejection");
 await fresh.page.getByRole('button',{name:'Assistant',exact:true}).click();
 await fresh.page.waitForFunction(()=>Copilot.loaded);
 const before=await fresh.page.evaluate(()=>Copilot.turns.length);
 let privateLeaked=false;
 fresh.page.on('request',r=>{if(r.url().includes('/api/assistant-')&&(r.postData()||'').includes('BROWSER-PRIVATE-998'))privateLeaked=true});
 await fresh.page.getByRole('textbox',{name:'Tell PeopleDesk what to do'}).fill('Message Ravi: BROWSER-PRIVATE-998 please check the launch');
 await fresh.page.getByRole('button',{name:'Send to PeopleDesk',exact:true}).click();
 await fresh.page.getByRole('button',{name:'Send private message',exact:true}).click();
 await fresh.page.getByText('BROWSER-PRIVATE-998 please check the launch',{exact:true}).waitFor();
 assert(!privateLeaked);
 const saved=await call(fresh,'assistant-history',{});
 assert(!JSON.stringify(saved).includes('BROWSER-PRIVATE-998'));
 console.log('PASS private assistant message remains outside server assistant history');
 await admin.page.getByRole('button',{name:'Assistant',exact:true}).click();
 await admin.page.setViewportSize({width:390,height:844});
 await admin.page.evaluate(()=>scrollTo(0,0));
 await admin.page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=1);
 await admin.page.screenshot({path:'tests/Assistant-mobile.png'});
 assert(await admin.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));

 await karan.page.setViewportSize({width:390,height:844});
 await karan.page.evaluate(()=>scrollTo(0,0));
 await karan.page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=1);
 await karan.page.screenshot({path:"tests/Employee-messages-mobile.png"});
 assert(await karan.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);
 console.log("PASS responsive portal and no browser exceptions");
 }finally{
 if(admin)try{await admin.page.evaluate(()=>fetch('/api/stop-local',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}));}catch{}
 if(browser)await browser.close();
 proc.kill();
 }
})().catch(e=>{console.error(e);process.exitCode=1});

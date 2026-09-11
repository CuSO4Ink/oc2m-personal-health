import assert from 'node:assert/strict';
const base=process.env.TEST_ORIGIN||'http://127.0.0.1:8787';
if(!['localhost','127.0.0.1'].includes(new URL(base).hostname))throw new Error('Use a local test instance.');
const tenant='test-'+Date.now();let checks=0;
async function request(path,{cookie='',method='GET',data,expected=200,otherTenant}={}){
 const headers={'oai-authenticated-user-id':otherTenant||tenant,...(cookie?{cookie}:{})};
 if(data&&!(data instanceof FormData))headers['Content-Type']='application/json';
 const res=await fetch(base+path,{method,headers,body:data instanceof FormData?data:data?JSON.stringify(data):undefined});
 const raw=await res.text();assert.equal(res.status,expected,`${method} ${path}: ${raw}`);checks++;
 let body;try{body=JSON.parse(raw)}catch{body=raw}return {res,body};
}
async function login(actor){return (await request('/api/session',{method:'POST',data:{actor}})).res.headers.get('set-cookie').split(';')[0]}
const root=await fetch(base);assert.equal(root.status,200);checks++;
await request('/api/records',{expected:401});
const patient=await login('patient-lin'),doctor=await login('doctor-wang'),wrong=await login('doctor-li'),other=await login('patient-zhou');
const form={title:'API test report',summary:'Original content',kind:'Lab report',date:'2026-09-11',source:'Test fixture'};
const {body:created}=await request('/api/records',{cookie:patient,method:'POST',data:form,expected:201});
const path='/api/records/'+encodeURIComponent(created.id);
await request(path,{cookie:doctor,expected:403});await request(path,{cookie:other,expected:403});
await request(path,{cookie:patient,method:'PATCH',data:{title:form.title,summary:'Updated content',version:1}});
await request(path,{cookie:patient,method:'PATCH',data:{title:'Stale edit',summary:'Must not save',version:1},expected:409});
const {body:edited}=await request(path,{cookie:patient});assert.equal(edited.record.version,2);assert.equal(edited.history.length,2);assert.equal(edited.history[1].summary,'Original content');checks+=3;
const upload=new FormData();upload.append('file',new File(['%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF'],'test.pdf',{type:'application/pdf'}));
await request(path+'/file',{cookie:patient,method:'POST',data:upload});
await request(path+'/file',{cookie:doctor,expected:403});
await request('/api/grants',{cookie:other,method:'POST',data:{doctor:'doctor-wang',records:[created.id],minutes:60},expected:403});
await request('/api/grants',{cookie:patient,method:'POST',data:{doctor:'doctor-wang',records:[created.id],minutes:60},expected:201});
const {body:visible}=await request('/api/records',{cookie:doctor});assert.equal(visible.records.length,1);assert.equal(visible.records[0].id,created.id);checks+=2;
await request(path,{cookie:doctor});await request(path+'/file',{cookie:doctor});await request(path,{cookie:wrong,expected:403});
await request(path,{cookie:doctor,method:'PATCH',data:{title:'Forbidden',summary:'Must not save',version:2},expected:403});
const {body:g}=await request('/api/grants',{cookie:patient});
await request('/api/grants',{cookie:patient,method:'DELETE',data:{id:g.grants[0].id}});
await request(path,{cookie:doctor,expected:403});await request(path+'/file',{cookie:doctor,expected:403});
const {body:hidden}=await request('/api/records',{cookie:doctor});assert.equal(hidden.records.length,0);checks++;
await request(path,{cookie:patient,otherTenant:'different-tenant',expected:401});
const {body:log}=await request('/api/logs',{cookie:patient});assert.ok(log.logs.some(l=>l.actor==='doctor-wang'&&l.result==='denied'));assert.ok(log.logs.some(l=>l.action==='Edit record'));checks+=2;
const patientAgain=await login('patient-lin');const {body:saved}=await request(path,{cookie:patientAgain});assert.equal(saved.record.summary,'Updated content');checks++;
// A replacement grant must leave only one effective permission to revoke.
for(let i=0;i<2;i++)await request('/api/grants',{cookie:patient,method:'POST',data:{doctor:'doctor-wang',records:[created.id],minutes:1},expected:201});
const {body:latest}=await request('/api/grants',{cookie:patient});assert.equal(latest.grants.filter(g=>g.record_id===created.id&&!g.revoked).length,1);checks++;
console.log(`Core workflow passed (${checks} checks). Waiting for the one-minute permission to expire.`);
await new Promise(r=>setTimeout(r,62000));
await request(path,{cookie:doctor,expected:403});await request(path+'/file',{cookie:doctor,expected:403});
console.log(`PASS: ${checks} checks, including real-time expiry, upload, history, role/tenant isolation, revocation and persistence across sessions.`);

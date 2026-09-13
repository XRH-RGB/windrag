/* Local demonstration only: role filtering here is an interaction, not security. */
window.WIND_DEMO=true;
const demoKey='windrag-demo-v2';
window.demoSession='operator';
function initialDemo(){return {role:'operator',docs:window.WIND_SEED.map((d,i)=>({...d,id:'seed-'+i,series:'seed-'+i,version:1,status:'published',expires:'',created:new Date().toISOString(),author:'内置示例',chunk_count:Math.max(1,Math.ceil(d.content.length/520)),valid:true})),histories:{},audit:[],users:Object.entries({operator:'运维人员',engineer:'工程师',librarian:'知识管理员',admin:'系统管理员'}).map(([r,name])=>({id:r,username:r,name,role:r,farms:r==='operator'?['北岭风场']:['北岭风场','海岬风场']}))}}
try{window.demoState=JSON.parse(localStorage.getItem(demoKey))||initialDemo()}catch{window.demoState=initialDemo()}
window.demoState.users.forEach(u=>{if(!u.password)u.password='Wind@2026!'});
if(!window.demoState.users.some(u=>u.username==='user'))window.demoState.users.push({id:'user',username:'user',name:'普通用户',role:'user',farms:['北岭风场','海岬风场'],password:'user123'});
window.demoState.settings=window.demoState.settings||{...windDefaults};
function saveDemo(){try{localStorage.setItem(demoKey,JSON.stringify(window.demoState))}catch{}}
function demoTokens(text){const words=(text.toLowerCase().match(/[a-z0-9_-]+/g)||[]);for(const s of text.match(/[\u4e00-\u9fff]+/g)||[])for(let i=0;i<s.length-1;i++)words.push(s.slice(i,i+2));return words}
async function demoAPI(path,body){
  const store=window.demoState;
  const ranks={user:0,operator:0,engineer:1,librarian:2,admin:3};
  if(path==='login'){const found=store.users.find(u=>u.username===body.username&&u.password===body.password);if(!found)throw Error('账号或密码不正确');window.demoSession=found.username;return {user:{...found,password:undefined}}}
  if(path==='logout'){window.demoSession=null;return {ok:true}}
  const user=store.users.find(u=>u.username===window.demoSession);if(!user)throw Error('请先登录');const rank=ranks[user.role];
  if(user.role==='admin')user.farms=['北岭风场','海岬风场'];
  const visible=d=>user.role==='admin'||((d.farm==='公共'||user.farms.includes(d.farm))&&rank>=ranks[d.min_role]);
  const record=(action,target='')=>{store.audit.unshift({id:Date.now(),actor:user.username,action,target,created:new Date().toISOString()});saveDemo()};
  const id=()=>globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+Math.random().toString(36).slice(2);
  const requireRank=n=>{if(rank<n)throw Error('当前演示角色没有此操作权限')};
  const history=store.histories[user.id]??(store.histories[user.id]=[]);
  if(path==='me')return {user:{...user,password:undefined},mode:'资料摘录',retrieval:'本地关键词检索',thresholds:store.settings};
  if(path==='settings'){if(!body)return {items:store.settings,editable:rank===3};requireRank(3);const values={...store.settings};for(const [k,v] of Object.entries(body)){if(!(k in windDefaults)||typeof v==='boolean'||v===null||v===''||!Number.isFinite(Number(v))||Number(v)<0||Number(v)>1)throw Error('阈值必须在 0 到 1 之间');values[k]=Math.round(Number(v)*10000)/10000}store.settings=values;record('修改检索阈值');return {items:store.settings}}

  if(path==='history')return {items:history};
  if(path==='docs')return {items:store.docs.filter(d=>visible(d)&&(rank>=1||d.status==='published')).map(d=>({...d,valid:!d.expires||d.expires>=new Date().toISOString().slice(0,10)}))};
  const faqs=(window.WIND_FAQS||[]).map(f=>({f,d:store.docs.find(d=>d.title===f.source_title&&visible(d)&&d.status==='published'&&(!d.expires||d.expires>=new Date().toISOString().slice(0,10))&&d.content===window.WIND_SEED.find(x=>x.title===f.source_title)?.content)})).filter(x=>x.d);
  if(path==='faqs')return {items:faqs.map(({f,d})=>({...f,farm:d.farm,min_role:d.min_role}))};
  if(path==='chat'){
    const question=String(body.question||'').trim();if(question.length<1||question.length>2000)throw Error('问题需为 1–2000 字符');
    if(body.farm&&!user.farms.includes(body.farm))throw Error('没有此风场的访问权限');
    let query=question;
    if(body.previous_id&&/它|这个|上述|那|继续/.test(question)){const prior=history.find(r=>r.id===body.previous_id);if(prior)query=prior.question+' '+question}
    const visibleDocs=store.docs.filter(d=>visible(d)&&d.status==='published'&&(!d.expires||d.expires>=new Date().toISOString().slice(0,10))&&(!body.farm||['公共',body.farm].includes(d.farm)));
    const computed=windDemoAnswer(question,query,user,visibleDocs,faqs,store.settings,body.farm);
    const result={...computed,id:id(),created:new Date().toISOString()};history.unshift(result);if(history.length>50)history.length=50;record('知识问答',result.id);return structuredClone(result);
  }
  if(path==='feedback'){const h=history.find(h=>h.id===body.id);if(!h)throw Error('记录不存在');h.feedback=body.value;record('问答反馈',body.id);return {ok:true}}
  if(path==='ingest'){
    requireRank(1);if(!body.title||body.title.length<2||String(body.content||'').trim().length<30)throw Error('标题至少 2 字，正文至少 30 字');
    if(body.farm!=='公共'&&!user.farms.includes(body.farm))throw Error('无权维护该风场');
    if(!(body.min_role in ranks)||ranks[body.min_role]>rank)throw Error('访问角色不正确');
    if(body.expires&&body.expires<new Date().toISOString().slice(0,10))throw Error('有效期不能早于今天');
    const series=body.series||id(),prior=store.docs.filter(d=>d.series===series);if(prior.some(d=>!visible(d)))throw Error('无权修订此资料');
    const doc={...body,id:id(),series,version:Math.max(0,...prior.map(d=>d.version))+1,status:'staged',created:new Date().toISOString(),author:user.username,valid:true,chunk_count:Math.max(1,Math.ceil(body.content.length/520))};store.docs.unshift(doc);record('导入候选知识',doc.id);return {id:doc.id,chunks:doc.chunk_count,status:'staged'};
  }
  if(path==='publish'){requireRank(2);const d=store.docs.find(d=>d.id===body.id);if(!d||!visible(d))throw Error('无权访问此资料');if(d.expires&&d.expires<new Date().toISOString().slice(0,10))throw Error('过期资料不能发布');const action=d.status==='retired'?'回滚知识':'发布知识';store.docs.filter(x=>x.series===d.series&&x.status==='published').forEach(x=>x.status='retired');d.status='published';record(action,d.id);return {ok:true}}
  if(path==='users'){requireRank(3);if(!body)return {items:store.users.map(u=>({...u,password:undefined}))};if(!/^[A-Za-z0-9_]{3,30}$/.test(body.username)||body.password.length<10||!body.farms.length)throw Error('请检查账号、密码与风场');if(store.users.some(u=>u.username===body.username))throw Error('账号已存在');store.users.push({id:id(),username:body.username,name:body.name,role:body.role,farms:body.farms,password:body.password});record('创建演示账号',body.username);return {ok:true}}
  if(path==='audit'){requireRank(2);return {items:store.audit.slice(0,100)}}
  throw Error('演示版不支持此操作');
}

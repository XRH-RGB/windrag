'use strict';
const windDefaults={faq_threshold:.90,bm25_threshold:.25,rerank_threshold:.30,confidence_threshold:.80};
const windDirect={
 greeting:['问候直出','你好，我是风知风电知识助手。可以向我咨询风机原理、巡检交接、告警资料或运行指标，也可以点击 FAQ 查看标准答案。'],
 thanks:['致谢直出','不客气！还有风电知识问题可以继续提问，涉及具体设备时请补充机型和机组信息。'],
 goodbye:['告别直出','再见！本次问答已保留，之后可以从最近问答中继续查看。'],
 out_of_scope:['业务越界直出','这个问题超出风电知识服务范围。我可以回答风机原理、运维资料、告警核对和知识管理问题，请换一个风电问题。'],
 permission_denied:['权限越界直出','当前角色无权访问所请求的风场资料。请联系系统管理员分配权限，本次不检索或返回受限内容。'],
 prompt_boundary:['指令越界直出','不能通过对话绕过访问规则或获取系统提示词、账号密码等内部信息。可以继续查询授权范围内的风电知识。'],
 control_action:['控制越界直出','该请求涉及机组保护或控制操作。本系统不执行这些动作，也不提供绕过保护的步骤，请由授权工程师按有效规程核实。'],
 realtime_status:['实时边界直出','尚未接入 SCADA 实时接口，无法确认当前功率、风速或发电量。请从授权监控系统获取带时间戳的数据；知识库可用于解释指标定义。']
};
function windNormalize(s){return s.toLowerCase().replace(/[^\p{L}\p{N}]/gu,'')}
function windTokenize(s){let arr=s.toLowerCase().match(/[a-z0-9_-]+/g)||[];for(const word of s.match(/[\u4e00-\u9fff]+/g)||[]){for(let i=0;i<word.length-1;i++)arr.push(word.slice(i,i+2));if(word.length===1)arr.push(word)}return arr}
function windFaqScore(a,b){a=windNormalize(a);b=windNormalize(b);if(a===b)return 1;if(JSON.stringify(a.match(/\d+/g))!==JSON.stringify(b.match(/\d+/g)))return 0;for(const n of ['不','没','未','否','必须'])if(a.includes(n)!==b.includes(n))return 0;if(Math.abs(a.length-b.length)>6)return 0;const x=new Set(windTokenize(a)),y=new Set(windTokenize(b));return 2*[...x].filter(t=>y.has(t)).length/Math.max(1,x.size+y.size)}
function windIntent(text,user){
 let label='knowledge_search';
 if(user.role!=='admin'&&['北岭风场','海岬风场'].some(f=>text.includes(f)&&!user.farms.includes(f)))label='permission_denied';
 else if(/系统提示词|system\s*prompt|忽略.{0,12}(规则|指令|权限)|绕过.{0,8}(登录|权限)|管理员密码|所有.*密码/i.test(text))label='prompt_boundary';
 else if(/(绕过|跳过|取消|解除|屏蔽).*(联锁|保护)|强制.*(启动|复位)|修改.*(保护|阈值)/.test(text))label='control_action';
 else if(/(现在|当前|今天|实时).*(功率|风速|发电量|状态)|实时数据/.test(text))label='realtime_status';
 else{const n=windNormalize(text);if(['你好','您好','嗨','哈喽','hello','hi','早上好','下午好','晚上好'].includes(n))label='greeting';else if(['谢谢','感谢','多谢','谢谢你','辛苦了','thanks','thankyou'].includes(n))label='thanks';else if(['再见','拜拜','回头见','bye','goodbye'].includes(n))label='goodbye';else if(/红烧肉|菜谱|做饭|写.{0,4}(情诗|小说)|旅游攻略|推荐股票|股票涨跌|星座运势|足球比分/.test(text))label='out_of_scope'}
 return {label,engine:'规则分流',confidence:null,scores:{},model:null,warning:'单文件演示未加载 BERT；不显示模型概率'};
}
function windSearch(query,docs,config){
 const rows=[];for(const d of docs)for(let i=0;i<d.content.length;i+=520){const chunk=d.content.slice(i,i+600),arr=windTokenize(d.title+' '+chunk),counts={};arr.forEach(t=>counts[t]=(counts[t]||0)+1);rows.push({doc:d,chunk,chunk_id:d.id+'-'+i,counts,length:arr.length})}
 const q=new Set(windTokenize(query)),freq={};rows.forEach(r=>Object.keys(r.counts).forEach(t=>freq[t]=(freq[t]||0)+1));const avg=rows.reduce((a,r)=>a+r.length,0)/Math.max(1,rows.length);
 for(const r of rows){let score=0;for(const t of q){let f=r.counts[t]||0;if(f)score+=Math.log(1+(rows.length-freq[t]+.5)/(freq[t]+.5))*f*2.2/(f+1.2*(.25+.75*r.length/Math.max(1,avg)))}r.raw_score=score;r.bm25_normalized=score/(score+6);r.coverage=[...q].filter(t=>r.counts[t]).length/Math.max(1,q.size);r.relevance=.65*r.bm25_normalized+.35*r.coverage;r.recalled=score>0&&r.bm25_normalized>=config.bm25_threshold}
 rows.sort((a,b)=>b.relevance-a.relevance);const selected=[],seen=new Set();for(const r of rows){if(r.recalled&&r.relevance>=config.rerank_threshold&&!seen.has(r.doc.id)){selected.push(r);seen.add(r.doc.id)}if(selected.length===3)break}
 const selectedIds=new Set(selected.map(r=>r.chunk_id));
 return {selected,metrics:{eligible_docs:docs.length,eligible_chunks:rows.length,candidate_chunks:rows.filter(r=>r.recalled).length,selected_docs:selected.length,source_share:docs.length?selected.length/docs.length:0,method:'BM25 / 本地计算',candidates:rows.slice(0,12).map(r=>({id:r.doc.id,title:r.doc.title,farm:r.doc.farm,version:r.doc.version,raw_score:r.raw_score,bm25_normalized:r.bm25_normalized,coverage:r.coverage,semantic:null,relevance:r.relevance,selected:selectedIds.has(r.chunk_id),reason:selectedIds.has(r.chunk_id)?'已引用':!r.recalled?'召回分不足':r.relevance<config.rerank_threshold?'综合相关度不足':'去重或 Top-3 截断'}))}};
}
function windDemoAnswer(question,query,user,docs,faqs,config,farm){
 const started=performance.now(),intent=windIntent(question,user),trace=[{step:'身份与范围',detail:user.role+' · '+(farm||'授权风场')},{step:'意图判断',detail:intent.engine+'：'+intent.label+'；'+intent.warning}];
 let answer='',mode='资料摘录',sources=[],faqMetric=null,retrieval=null;
 if(windDirect[intent.label]){[mode,answer]=windDirect[intent.label];trace.push({step:'直接响应',detail:mode+'，跳过 FAQ、检索和模型生成'})}
 else{
  let best=null;for(const {f,d} of faqs){if(farm&&!['公共',farm].includes(d.farm))continue;const score=Math.max(...[f.question,...f.aliases].map(q=>windFaqScore(query,q)));if(!best||score>best.score)best={score,f,d}}
  faqMetric={score:best?.score||0,threshold:config.faq_threshold,matched:Boolean(best&&best.score>0&&best.score>=config.faq_threshold)};
  if(faqMetric.matched){mode='FAQ 直出';answer=best.f.answer+' [1]';faqMetric.id=best.f.id;if(best.score===1){intent.label='FAQ_QUERY';intent.engine='FAQ 精确路由';intent.warning='跳过 BERT 与检索准备';trace[1]={step:'Stage 1 · FAQ 精确路由',detail:intent.warning}}sources=[{id:best.d.id,title:best.d.title,version:best.d.version,farm:best.d.farm,excerpt:best.d.content,citation:1,relevance:best.score}];trace.push({step:best.score===1?'Stage 1 · FAQ 精确直出':'Stage 3 · FAQ 阈值匹配',detail:best.f.id+'：'+(best.score*100).toFixed(1)+'% ≥ '+(config.faq_threshold*100).toFixed(1)+'%，来源与权限通过'},{step:'标准答案直出',detail:'跳过文档检索与生成'})}
  else{
   trace.push({step:'FAQ 匹配',detail:'最佳 '+(faqMetric.score*100).toFixed(1)+'%，未达到适用直出条件'});
   const search=windSearch(query,docs,config);retrieval=search.metrics;
   sources=search.selected.map((r,i)=>({id:r.doc.id,title:r.doc.title,version:r.doc.version,farm:r.doc.farm,citation:i+1,excerpt:r.chunk,relevance:r.relevance,bm25_normalized:r.bm25_normalized,coverage:r.coverage}));
   answer=sources.length?'根据当前可访问的资料，相关依据如下：\n\n'+sources.map(s=>`[${s.citation}] ${s.excerpt}`).join('\n\n'):'当前授权知识中没有达到检索阈值的依据。请补充机型、部件或资料名称，也可联系知识管理员补充资料。';if(!sources.length)mode='证据不足澄清';
   trace.push({step:'授权过滤与检索',detail:'可见 '+docs.length+' 份资料，返回 '+sources.length+' 份'},{step:'得分门槛',detail:'BM25 归一化 ≥ '+config.bm25_threshold+'；综合相关度 ≥ '+config.rerank_threshold},{step:'证据交付',detail:'返回原文摘录；百分比为匹配得分，不是准确率'})
  }
 }
 trace.push({step:'归档',detail:'保存回答、引用与本次阈值快照'});
 return {question,answer,mode,sources,trace,metrics:{intent,faq:faqMetric,retrieval,thresholds:{...config},elapsed_ms:Math.round((performance.now()-started)*100)/100}};
}

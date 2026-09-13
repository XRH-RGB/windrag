"""Routing, persisted threshold validation and an optional real BERT HTTP adapter."""
import json, math, os, re, hashlib
from collections import Counter, defaultdict
from datetime import date
from urllib.request import Request, urlopen

DEFAULTS={'faq_threshold':.90,'bm25_threshold':.25,'rerank_threshold':.30,'confidence_threshold':.80}
LABELS={'greeting','thanks','goodbye','out_of_scope','knowledge_search','realtime_status','control_action'}
DIRECT={
 'greeting':('问候直出','你好，我是风知风电知识助手。可以向我咨询风机原理、巡检交接、告警资料或运行指标，也可以点击下方 FAQ 查看标准答案。'),
 'thanks':('致谢直出','不客气！如果还有风电知识问题，可以继续提问；涉及具体设备时请补充机型和机组信息。'),
 'goodbye':('告别直出','再见！本次问答已保留，你可以稍后从最近问答中继续查看。'),
 'out_of_scope':('业务越界直出','这个问题超出风电知识服务范围。我可以回答风机原理、运维资料、告警核对和知识管理相关问题，请换一个风电问题。'),
 'permission_denied':('权限越界直出','当前账号无权访问所请求的风场或管理信息。请联系系统管理员分配相应权限，本次不会检索或返回受限资料。'),
 'prompt_boundary':('指令越界直出','不能通过对话绕过访问规则或读取系统提示词、账号密码等内部信息。你可以继续查询授权范围内的风电知识。'),
 'control_action':('控制越界直出','该请求涉及机组保护、控制或参数修改。本系统不执行这些操作，也不提供绕过保护的步骤，请由授权工程师按有效规程核实处理。'),
 'realtime_status':('实时边界直出','尚未接入 SCADA 实时接口，无法确认当前功率、风速或发电量。请从授权监控系统获取机组编号、时间戳与数据；知识库可用于解释指标定义。')}

def normalize(text):return re.sub(r'[^\w]','',text.lower()).replace('_','')
def token_set(text):
    parts=re.findall(r'[a-z0-9_-]+',text.lower())
    for seq in re.findall(r'[\u4e00-\u9fff]+',text):
        parts.extend(seq[i:i+2] for i in range(len(seq)-1))
        if len(seq)==1:parts.append(seq)
    return set(parts)
def faq_similarity(a,b):
    a,b=normalize(a),normalize(b)
    if a==b:return 1.0
    # Additional conditions, numbers or negations must not become a fuzzy FAQ hit.
    if re.findall(r'\d+',a)!=re.findall(r'\d+',b):return 0.0
    if {x for x in ['不','没','未','否','必须'] if x in a}!={x for x in ['不','没','未','否','必须'] if x in b}:return 0.0
    if abs(len(a)-len(b))>6:return 0.0
    x,y=token_set(a),token_set(b)
    return 2*len(x&y)/max(1,len(x)+len(y))

def settings(db):
    row=db.execute("SELECT value FROM settings WHERE key='retrieval'").fetchone()
    return {**DEFAULTS,**(json.loads(row[0]) if row else {})}
def save_settings(db,body):
    unknown=set(body)-set(DEFAULTS)
    if unknown:raise ValueError('未知配置项')
    values=settings(db)
    for k,v in body.items():
        if isinstance(v,bool):raise ValueError('阈值不能为布尔值')
        n=float(v)
        if not math.isfinite(n) or not 0<=n<=1:raise ValueError('阈值应在 0–1 内')
        values[k]=round(n,4)
    db.execute("INSERT INTO settings VALUES('retrieval',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(values),))
    return values

def boundary(text,user,farms):
    if user['role']!='admin' and any(f in text and f not in user['farms'] for f in farms):return 'permission_denied'
    if re.search(r'系统提示词|system\s*prompt|忽略.{0,12}(规则|指令|权限)|绕过.{0,8}(登录|权限)|管理员密码|所有.*密码',text,re.I):return 'prompt_boundary'
    if re.search(r'(绕过|跳过|取消|解除|屏蔽).*(联锁|保护)|强制.*(启动|复位)|修改.*(保护|阈值)',text):return 'control_action'
    if re.search(r'(现在|当前|今天|实时).*(功率|风速|发电量|状态)|实时数据',text):return 'realtime_status'
    return None

def classify(text):
    url=os.environ.get('WINDRAG_BERT_URL','').strip()
    warning=''
    if url:
        try:
            req=Request(url,data=json.dumps({'text':text}).encode(),headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=12) as r:result=json.loads(r.read(512000))
            probs=result['scores']
            if result.get('model_type')!='bert' or set(probs)!=LABELS:raise ValueError('不是约定的 BERT 分类响应')
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in probs.values()):raise ValueError('概率无效')
            if abs(sum(probs.values())-1)>.01:raise ValueError('概率和不为1')
            label=max(probs,key=probs.get)
            return {'label':label,'confidence':probs[label],'scores':probs,'engine':'BERT','model':str(result.get('model','local')),'warning':''}
        except Exception:warning='BERT 服务不可用，已回退规则判断'
    else:warning='未配置 BERT 模型，当前按规则分流；不显示模型概率'
    n=normalize(text)
    if n in {'你好','您好','嗨','哈喽','hello','hi','早上好','下午好','晚上好'}:label='greeting'
    elif n in {'谢谢','感谢','多谢','谢谢你','辛苦了','thanks','thankyou'}:label='thanks'
    elif n in {'再见','拜拜','回头见','bye','goodbye'}:label='goodbye'
    elif re.search(r'红烧肉|菜谱|做饭|写.{0,4}(情诗|小说)|旅游攻略|推荐股票|股票涨跌|星座运势|足球比分',text):label='out_of_scope'
    else:label='knowledge_search'
    return {'label':label,'confidence':None,'scores':{},'engine':'规则分流','model':None,'warning':warning}

def search(db,user,query,farm,allowed,tokenize,embed,cosine,config):
    rows=[dict(r) for r in db.execute("SELECT c.id chunk_id,c.content chunk,c.vector,d.* FROM chunks c JOIN docs d ON d.id=c.doc_id WHERE d.status='published' AND (d.expires='' OR d.expires>=?)",(date.today().isoformat(),)) if allowed(user,r) and (not farm or r['farm'] in ['公共',farm])]
    q=token_set(query);terms=[Counter(tokenize(r['title']+' '+r['chunk'])) for r in rows]
    avg=sum(sum(t.values()) for t in terms)/max(1,len(terms));freq=Counter(k for t in terms for k in t)
    for r,t in zip(rows,terms):
        raw=sum(math.log(1+(len(rows)-freq[k]+.5)/(freq[k]+.5))*t[k]*2.2/(t[k]+1.2*(.25+.75*sum(t.values())/max(1,avg))) for k in q if t[k])
        r.update(raw_score=raw,bm25_normalized=raw/(raw+6),coverage=len(q&set(t))/max(1,len(q)),semantic=None)
    lexical=sorted([r for r in rows if r['raw_score']>0 and r['bm25_normalized']>=config['bm25_threshold']],key=lambda r:r['raw_score'],reverse=True)
    candidates=list(lexical);method='BM25';warning=''
    if os.environ.get('WINDRAG_EMBED_BASE_URL') and rows:
        try:
            signature=hashlib.sha256((os.environ.get('WINDRAG_EMBED_BASE_URL','')+'|'+os.environ.get('WINDRAG_EMBED_MODEL','')).encode()).hexdigest();missing=[]
            for r in rows:
                cache=json.loads(r['vector']) if r['vector'] else {}
                if cache.get('model')==signature:r['vec']=cache['vector']
                else:missing.append(r)
            for offset in range(0,len(missing),24):
                batch=missing[offset:offset+24]
                for r,v in zip(batch,embed([r['title']+'\n'+r['chunk'] for r in batch])):
                    r['vec']=v;db.execute('UPDATE chunks SET vector=? WHERE id=?',(json.dumps({'model':signature,'vector':v}),r['chunk_id']))
            qv=embed([query])[0]
            for r in rows:r['semantic']=max(0,min(1,cosine(qv,r['vec'])))
            dense=sorted([r for r in rows if r['semantic']>=float(os.environ.get('WINDRAG_EMBED_MIN_SCORE','.35'))],key=lambda r:r['semantic'],reverse=True)[:12]
            fusion=defaultdict(float);lookup={r['chunk_id']:r for r in rows}
            for stream in [lexical,dense]:
                for i,r in enumerate(stream):fusion[r['chunk_id']]+=1/(61+i)
            candidates=[lookup[k] for k in sorted(fusion,key=fusion.get,reverse=True)];method='BM25 + 向量 / RRF'
        except Exception:warning='向量服务异常，回退 BM25'
    candidate_ids={r['chunk_id'] for r in candidates};chosen=[];seen=set()
    for r in rows:
        r['relevance']=.65*max(r['bm25_normalized'],r['semantic'] or 0)+.35*r['coverage']
    candidates.sort(key=lambda r:r['relevance'],reverse=True)
    for r in candidates:
        if r['relevance']>=config['rerank_threshold'] and r['id'] not in seen:
            chosen.append(r);seen.add(r['id'])
            if len(chosen)==3:break
    selected={r['chunk_id'] for r in chosen}
    report=[]
    for r in sorted(rows,key=lambda r:r['relevance'],reverse=True)[:12]:
        reason='已引用' if r['chunk_id'] in selected else '召回分不足' if r['chunk_id'] not in candidate_ids else '综合相关度不足' if r['relevance']<config['rerank_threshold'] else '去重或 Top-3 截断'
        report.append({'id':r['id'],'title':r['title'],'farm':r['farm'],'version':r['version'],'raw_score':round(r['raw_score'],4),'bm25_normalized':round(r['bm25_normalized'],4),'coverage':round(r['coverage'],4),'semantic':r['semantic'],'relevance':round(r['relevance'],4),'selected':r['chunk_id'] in selected,'reason':reason})
    count=len({r['id'] for r in rows})
    metrics={'eligible_docs':count,'eligible_chunks':len(rows),'candidate_chunks':len(candidates),'selected_docs':len(chosen),'source_share':len(chosen)/count if count else 0,'candidates':report,'method':method}
    return chosen,method,warning,metrics

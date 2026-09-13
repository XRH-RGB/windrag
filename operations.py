"""Wind operations: persistent measurements, quality, baseline forecast and work orders."""
import csv, io, json, math, random, statistics, secrets
from datetime import datetime, timedelta
from urllib.parse import parse_qs

METRICS={'wind_speed':('风速','m/s',0,40),'power':('功率','kW',0,6000),'temperature':('温度','℃',-40,120),'rpm':('转速','rpm',0,30)}
STATES=['正常','注意','告警','故障','停机']
WRITERS={'admin','operator','engineer'}

def timestamp():return datetime.now().isoformat(timespec='seconds')
def dumps(x):return json.dumps(x,ensure_ascii=False,allow_nan=False)
def ident():return secrets.token_hex(8)
def initialize(db,s):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS roles(name TEXT PRIMARY KEY,title TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS wind_farms(id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,region TEXT,capacity REAL,manager TEXT,commissioned TEXT,status TEXT,notes TEXT);
    CREATE TABLE IF NOT EXISTS turbines(id TEXT PRIMARY KEY,name TEXT NOT NULL,farm_id TEXT REFERENCES wind_farms(id),model TEXT,rated_power REAL,location TEXT,commissioned TEXT,status TEXT);
    CREATE TABLE IF NOT EXISTS wind_data(id INTEGER PRIMARY KEY,turbine_id TEXT REFERENCES turbines(id),time TEXT NOT NULL,wind_speed REAL,power REAL,temperature REAL,rpm REAL,status TEXT,batch_id TEXT);
    CREATE INDEX IF NOT EXISTS idx_wind_data_turbine_time ON wind_data(turbine_id,time);
    CREATE TABLE IF NOT EXISTS data_batches(id TEXT PRIMARY KEY,owner TEXT,name TEXT,raw TEXT,cleaned TEXT,report TEXT,status TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY,turbine_id TEXT REFERENCES turbines(id),time TEXT,metric TEXT,value REAL,normal_range TEXT,level TEXT,status TEXT,handler TEXT,note TEXT,handled_at TEXT,UNIQUE(turbine_id,time,metric));
    CREATE TABLE IF NOT EXISTS maintenance_records(id TEXT PRIMARY KEY,turbine_id TEXT REFERENCES turbines(id),kind TEXT,time TEXT,problem TEXT,handler TEXT,method TEXT,result TEXT,status TEXT,notes TEXT);
    CREATE TABLE IF NOT EXISTS prediction_results(id TEXT PRIMARY KEY,turbine_id TEXT REFERENCES turbines(id),created TEXT,actor TEXT,result TEXT);
    CREATE TABLE IF NOT EXISTS operation_logs(id INTEGER PRIMARY KEY,actor TEXT,role TEXT,action TEXT,module TEXT,created TEXT,result TEXT);
    CREATE TABLE IF NOT EXISTS system_parameters(key TEXT PRIMARY KEY,value TEXT);
    ''')
    if 'enabled' not in [r[1] for r in db.execute('PRAGMA table_info(users)')]:db.execute('ALTER TABLE users ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1')
    for role,title in s.ROLES.items():db.execute('INSERT OR REPLACE INTO roles VALUES(?,?)',(role,title))
    # One-time upgrade changes only the previously supplied default passwords.
    # This keeps manually changed passwords intact while aligning older seeded
    # databases with the credentials shown on the login page.
    migrated=[]
    for name,pw in [('admin','admin123'),('operator','operator123'),('user','user123')]:
        row=db.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone()
        if not row:
            db.execute('INSERT INTO users(id,username,name,role,farms,password) VALUES(?,?,?,?,?,?)',(ident(),name,s.ROLES[name],name,dumps(s.FARMS if name!='operator' else s.FARMS[:1]),s.password_hash(pw)))
            migrated.append((name,pw))
        elif s.check_password('Wind@2026!',row['password']):
            db.execute('UPDATE users SET password=? WHERE id=?',(s.password_hash(pw),row['id']))
            migrated.append((name,pw))
    if migrated:
        account_file=s.DATA/'首次登录账号.txt'
        try:
            text=account_file.read_text(encoding='utf-8')
            for name,pw in migrated:
                text=text.replace(f'账号：{name}\n密码：Wind@2026!',f'账号：{name}\n密码：{pw}')
                if f'账号：{name}' not in text:
                    text += f'\n\n{s.ROLES[name]}\n账号：{name}\n密码：{pw}\n'
            account_file.write_text(text,encoding='utf-8')
        except OSError:pass
    for key,value in [('temperature_limit',80),('rpm_limit',22),('wind_limit',25),('platform_name','风电智能运维与数据分析平台')]:db.execute('INSERT OR IGNORE INTO system_parameters VALUES(?,?)',(key,dumps(value)))
    if not db.execute('SELECT 1 FROM wind_farms').fetchone():
        for i,name in enumerate(s.FARMS):db.execute('INSERT INTO wind_farms VALUES(?,?,?,?,?,?,?,?)',(f'F{i+1}',name,['河北张家口','江苏盐城'][i],15000,['宋钰','张凇皓'][i],'2023-06-01','运行','课程演示风场'))
        rng=random.Random(20260910);start=datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=6)
        for i in range(10):
            tid=f'WT{i+1:02d}';status=STATES[i%5]
            db.execute('INSERT INTO turbines VALUES(?,?,?,?,?,?,?,?)',(tid,f'{i+1:02d} 号风机',f'F{i//5+1}','W-3000',3000,f'{114.1+i*.02:.3f}, {40.2+i*.01:.3f}','2023-06-01',status))
            rows=[]
            for h in range(168):
                wind=max(.2,8+3*math.sin(h/9+i)+rng.gauss(0,.65));power=min(3000,max(0,70*(wind-3)**2+rng.gauss(0,45)));temp=40+power/110+rng.gauss(0,2);rpm=min(20,wind*1.45)
                st='正常'
                if h in (145,166) and i in (1,3,6):temp=93+i;st='告警'
                if h==167:st=status;power=0 if st in ('故障','停机') else power
                rows.append((tid,(start+timedelta(hours=h)).isoformat(timespec='seconds'),round(wind,2),round(power,2),round(temp,2),round(rpm,2),st,'seed'))
            db.executemany('INSERT INTO wind_data(turbine_id,time,wind_speed,power,temperature,rpm,status,batch_id) VALUES(?,?,?,?,?,?,?,?)',rows)
            for kind in ['巡检','维修','故障']:
                db.execute('INSERT INTO maintenance_records VALUES(?,?,?,?,?,?,?,?,?,?)',(ident(),tid,kind,timestamp(),'例行核对温度与运行记录','operator','检查记录并安排现场复核','记录已归档','已完成','课程示例记录'))
        db.execute("INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?)",(ident(),'WT02',rows[-2][1],'temperature',94,'≤ 80 ℃','重要','未处理','','',''))
        db.execute("INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?)",(ident(),'WT04',rows[-1][1],'rpm',24,'≤ 22 rpm','一般','处理中','operator','安排巡检',timestamp()))
    if not db.execute('SELECT 1 FROM prediction_results').fetchone():
        for tid in ['WT01','WT06']:
            data=[dict(r) for r in db.execute('SELECT * FROM wind_data WHERE turbine_id=? ORDER BY time',(tid,))]
            if len(data)>=12:db.execute('INSERT INTO prediction_results VALUES(?,?,?,?,?)',(ident(),tid,timestamp(),'系统初始化',dumps(forecast(data,12,3000))))
    db.execute('PRAGMA optimize')

def log(db,u,action,module,result='成功'):
    db.execute('INSERT INTO operation_logs(actor,role,action,module,created,result) VALUES(?,?,?,?,?,?)',(u['username'],u['role'],action,module,timestamp(),result))

def scope(db,u):
    return [r[0] for r in db.execute('SELECT id FROM wind_farms') if u['role']=='admin' or db.execute('SELECT name FROM wind_farms WHERE id=?',(r[0],)).fetchone()[0] in u['farms']]

def machines(db,u):
    farms=scope(db,u)
    return [dict(r) for r in db.execute('SELECT t.*,f.name AS farm_name FROM turbines t JOIN wind_farms f ON t.farm_id=f.id ORDER BY t.id') if r['farm_id'] in farms]

def measurements(db,u,q):
    allowed={r['id'] for r in machines(db,u)}
    clauses=[];args=[]
    for key,col in [('turbine','turbine_id'),('status','status')]:
        if q.get(key):clauses.append(col+'=?');args.append(q[key])
    if q.get('start'):clauses.append('time>=?');args.append(q['start'])
    if q.get('end'):clauses.append('time<=?');args.append(q['end']+'T23:59:59' if len(q['end'])==10 else q['end'])
    sql='SELECT * FROM wind_data'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY time,id'
    farm_tids={r['id'] for r in machines(db,u) if not q.get('farm') or r['farm_id']==q['farm']}
    return [dict(r) for r in db.execute(sql,args) if r['turbine_id'] in allowed & farm_tids and (not q.get('q') or q['q'].lower() in (r['turbine_id']+' '+r['time']+' '+r['status']).lower())]

def page(rows,q):
    size=min(100,max(1,int(q.get('size',20))));number=max(1,int(q.get('page',1)));total=len(rows)
    number=min(number,max(1,math.ceil(total/size)))
    return {'items':rows[(number-1)*size:number*size],'total':total,'page':number,'size':size}

def stats(rows):
    out={}
    for key in METRICS:
        vals=[r[key] for r in rows if isinstance(r.get(key),(int,float)) and math.isfinite(r[key])]
        out[key]={'count':len(vals),'mean':round(statistics.mean(vals),3) if vals else None,'min':min(vals) if vals else None,'max':max(vals) if vals else None,'std':round(statistics.pstdev(vals),3) if vals else None}
    return out

def energy(rows):
    groups={};total=0
    for r in rows:groups.setdefault(r['turbine_id'],{})[r['time']]=r
    for group in groups.values():
        arr=sorted(group.values(),key=lambda r:r['time'])
        for a,b in zip(arr,arr[1:]):
            hours=(datetime.fromisoformat(b['time'])-datetime.fromisoformat(a['time'])).total_seconds()/3600
            if 0<hours<=6 and a['power'] is not None and b['power'] is not None:total+=(a['power']+b['power'])/2*hours
    return round(total,2)

def quality(rows):
    counts={'rows':len(rows),'missing':0,'outliers':0,'duplicates':0,'types':0,'times':0};seen=set()
    for r in rows:
        pair=(r.get('turbine_id'),r.get('time'))
        counts['duplicates']+=pair in seen;seen.add(pair)
        try:datetime.fromisoformat(str(r.get('time','')))
        except (ValueError,TypeError):counts['times']+=1
        for k,(_,_,lo,hi) in METRICS.items():
            val=r.get(k)
            if val is None or val=='':counts['missing']+=1;continue
            try:
                n=float(val)
                if not math.isfinite(n):raise ValueError()
                if not lo<=n<=hi:counts['outliers']+=1
            except (ValueError,TypeError):counts['types']+=1
    return counts

def clean(rows):
    means={}
    for k,(_,_,lo,hi) in METRICS.items():
        nums=[]
        for r in rows:
            try:
                v=float(r.get(k))
                if lo<=v<=hi and math.isfinite(v):nums.append(v)
            except (ValueError,TypeError):pass
        means[k]=statistics.mean(nums) if nums else (lo+hi)/2
    out={}
    for row in rows:
        r=dict(row)
        try:
            dt=datetime.fromisoformat(r['time'])
            if dt.tzinfo is not None:continue
            r['time']=dt.isoformat(timespec='seconds')
        except (ValueError,TypeError):continue
        for k,(_,_,lo,hi) in METRICS.items():
            try:v=float(r.get(k));v=v if math.isfinite(v) else means[k]
            except (ValueError,TypeError):v=means[k]
            r[k]=round(max(lo,min(hi,v)),3)
        r['status']=r.get('status') if r.get('status') in STATES else '正常'
        out[(r['turbine_id'],r['time'])]=r
    return sorted(out.values(),key=lambda x:(x['time'],x['turbine_id']))

def forecast(rows,horizon,rated):
    rows=[r for r in rows if isinstance(r.get('power'),(int,float))]
    if len(rows)<12:raise ValueError('至少需要 12 条有效数据')
    # Chronological holdout; persistence baseline uses only the previous observed power.
    split=max(8,int(len(rows)*.8));test=rows[split:];train=rows[:split]
    comparisons=[{'time':r['time'],'actual':r['power'],'predicted':rows[split+i-1]['power']} for i,r in enumerate(test)]
    errors=[r['predicted']-r['actual'] for r in comparisons];mean=statistics.mean(r['actual'] for r in comparisons)
    denom=sum((r['actual']-mean)**2 for r in comparisons)
    metrics={'MAE':round(statistics.mean(abs(e) for e in errors),3),'RMSE':round(math.sqrt(statistics.mean(e*e for e in errors)),3),'R2':round(1-sum(e*e for e in errors)/denom,4) if denom else None}
    last=datetime.fromisoformat(rows[-1]['time']);diffs=[(datetime.fromisoformat(b['time'])-datetime.fromisoformat(a['time'])).total_seconds() for a,b in zip(rows,rows[1:])];step=statistics.median([d for d in diffs if d>0]) if any(d>0 for d in diffs) else 3600
    value=max(0,min(rated,rows[-1]['power']))
    return {'model':'持续性时间序列基线','explanation':'回测用上一时刻实际功率预测下一时刻；未来预测保持最后一次观测功率。误差基于最后 20% 时间段。','train_count':len(train),'test_count':len(test),'metrics':metrics,'history':rows[-60:],'comparison':comparisons,'future':[{'time':(last+timedelta(seconds=step*(i+1))).isoformat(timespec='seconds'),'predicted':round(value,2)} for i in range(horizon)]}

def handle(db,u,path,write,b,query,s):
    q={k:v[-1] for k,v in parse_qs(query).items()};p=path.removeprefix('/api/ops/');allowed_turbines=machines(db,u);tids={t['id'] for t in allowed_turbines}
    def require(roles):
        if u['role'] not in roles:raise s.APIError(403,'当前角色没有此操作权限')
    def turbine(tid):
        if tid not in tids:raise s.APIError(403,'风机不存在或无权访问')
    def text(key,default='',limit=200):return str(b.get(key,default)).strip()[:limit]
    def number(key,lo,hi,default=0):
        x=float(b.get(key,default))
        if not math.isfinite(x) or not lo<=x<=hi:raise s.APIError(400,key+' 超出允许范围')
        return x
    def datevalue(key,default=''):
        value=text(key,default)
        if value:datetime.fromisoformat(value)
        return value
    if p=='meta' and not write:return {'farms':[dict(r) for r in db.execute('SELECT * FROM wind_farms') if r['id'] in scope(db,u)],'turbines':allowed_turbines,'metrics':METRICS,'source':'固定种子课程数据 + 用户导入数据','parameters':{r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM system_parameters')}}
    if p=='farms':
        if not write:
            return {'items':[dict(r,turbine_count=db.execute('SELECT COUNT(*) FROM turbines WHERE farm_id=?',(r['id'],)).fetchone()[0]) for r in db.execute('SELECT * FROM wind_farms') if r['id'] in scope(db,u)]}
        require({'admin'});fid=text('id') or ident();action=text('action','save')
        if action=='delete':
            if db.execute('SELECT 1 FROM turbines WHERE farm_id=?',(fid,)).fetchone():raise s.APIError(409,'请先处理风场下的风机，不能删除有设备的风场')
            db.execute('DELETE FROM wind_farms WHERE id=?',(fid,))
        else:
            if not text('name'):raise s.APIError(400,'请填写风场名称')
            db.execute('INSERT INTO wind_farms VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,region=excluded.region,capacity=excluded.capacity,manager=excluded.manager,commissioned=excluded.commissioned,status=excluded.status,notes=excluded.notes',(fid,text('name'),text('region'),number('capacity',0,10000000),text('manager'),datevalue('commissioned'),text('status','运行'),text('notes')))
        log(db,u,action+' 风场','风场管理');return {'ok':True,'id':fid}
    if p=='turbines':
        if not write:
            rows=[]
            for t in allowed_turbines:
                current=db.execute('SELECT * FROM wind_data WHERE turbine_id=? ORDER BY time DESC,id DESC LIMIT 1',(t['id'],)).fetchone()
                rows.append(dict(t,current=dict(current) if current else None))
            return page([t for t in rows if (not q.get('farm') or t['farm_id']==q['farm']) and (not q.get('status') or (t['current'] or t)['status']==q['status']) and q.get('q','').lower() in (t['id']+t['name']).lower()],q)
        require({'admin'});tid=text('id') or ident()
        if text('action')=='delete':
            if db.execute('SELECT 1 FROM wind_data WHERE turbine_id=?',(tid,)).fetchone():raise s.APIError(409,'该风机已有运行记录，不能删除')
            db.execute('DELETE FROM turbines WHERE id=?',(tid,))
        else:
            if text('farm_id') not in scope(db,u) or not text('name'):raise s.APIError(400,'请选择有效风场并填写风机名称')
            if text('status','正常') not in STATES:raise s.APIError(400,'状态无效')
            db.execute('INSERT INTO turbines VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,farm_id=excluded.farm_id,model=excluded.model,rated_power=excluded.rated_power,location=excluded.location,commissioned=excluded.commissioned,status=excluded.status',(tid,text('name'),text('farm_id'),text('model'),number('rated_power',1,100000,3000),text('location'),datevalue('commissioned'),text('status','正常')))
        log(db,u,'维护风机','风机管理');return {'ok':True}
    if p=='data' and not write:return page(measurements(db,u,q),q)
    if p=='dashboard' and not write:
        rows=measurements(db,u,{});latest={};daily={}
        for r in rows:latest[r['turbine_id']]=r
        today=datetime.now().date().isoformat();dayrows=[r for r in rows if r['time'].startswith(today)]
        for r in dayrows:
            x=daily.setdefault(r['time'],{'time':r['time'],'power':0,'wind':[]});x['power']+=r['power'] or 0;x['wind'].append(r['wind_speed'] or 0)
        alerts=[dict(r) for r in db.execute('SELECT * FROM alerts ORDER BY time DESC') if r['turbine_id'] in tids]
        states={k:sum(r['status']==k for r in latest.values()) for k in STATES}
        return {'kpis':{'风场数量':len(scope(db,u)),'风机总数':len(tids),'正常运行':states['正常'],'停机数量':states['停机'],'故障数量':states['故障'],'待处理告警':sum(a['status']!='已处理' for a in alerts),'当前功率 kW':round(sum(r['power'] or 0 for r in latest.values()),1),'今日发电 kWh':energy(dayrows),'累计发电 kWh':energy(rows),'平均风速 m/s':round(statistics.mean([r['wind_speed'] or 0 for r in latest.values()]),2) if latest else 0},'states':states,'levels':{k:sum(a['level']==k for a in alerts) for k in ['提示','一般','重要','严重']},'trend':[dict(x,wind_speed=statistics.mean(x.pop('wind'))) for x in daily.values()],'scatter':rows[-300:],'ranking':[{'name':tid,'value':energy([r for r in rows if r['turbine_id']==tid])} for tid in sorted(tids)],'alerts':alerts[:5],'maintenance':[dict(r) for r in db.execute('SELECT * FROM maintenance_records ORDER BY time DESC') if r['turbine_id'] in tids][:5],'source':'历史观测快照 · 课程演示数据','as_of':max((r['time'] for r in rows),default='')}
    if p=='import/preview' and write:
        require({'admin'});content=text('content',limit=900000)
        if not text('name').lower().endswith('.csv'):raise s.APIError(400,'请选择 CSV 文件')
        reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
        required={'turbine_id','time',*METRICS}
        if not required.issubset(reader.fieldnames or []):raise s.APIError(400,'CSV 缺少字段：'+','.join(sorted(required-set(reader.fieldnames or []))))
        rows=list(reader)
        if not rows or len(rows)>5000:raise s.APIError(400,'CSV 需包含 1–5000 行数据')
        if any(r.get('turbine_id') not in tids for r in rows):raise s.APIError(400,'CSV 包含未知或无权限的风机编号')
        if any(None in r for r in rows):raise s.APIError(400,'CSV 存在多余列，请检查逗号和引号')
        bid=ident();report=quality(rows)
        db.execute('INSERT INTO data_batches VALUES(?,?,?,?,?,?,?,?)',(bid,u['id'],text('name'),dumps(rows),'',dumps(report),'预览',timestamp()))
        log(db,u,'上传 CSV：'+str(len(rows))+' 行','数据导入');return {'id':bid,'report':report,'preview':rows[:30]}
    if p=='batches' and not write:
        require({'admin'});return {'items':[{'id':r['id'],'name':r['name'],'status':r['status'],'created':r['created'],'report':json.loads(r['report'])} for r in db.execute('SELECT * FROM data_batches ORDER BY created DESC')]}
    if p in ('import/confirm','data/clean') and write:
        require({'admin'});row=db.execute('SELECT * FROM data_batches WHERE id=?',(text('id'),)).fetchone()
        if not row:raise s.APIError(404,'导入批次不存在')
        raw=json.loads(row['raw']);before=quality(raw)
        if p=='import/confirm':
            if row['status']!='预览':raise s.APIError(409,'批次已确认，请勿重复提交')
            db.execute('UPDATE data_batches SET status=? WHERE id=?',('待处理',row['id']));log(db,u,'确认原始数据入库','数据导入');return {'ok':True,'report':before,'status':'待处理'}
        if row['status']=='预览':raise s.APIError(409,'请先确认导入')
        cleaned=clean(raw)
        if not cleaned:raise s.APIError(400,'没有可用时间记录，请修正 CSV')
        if any(r['turbine_id'] not in tids for r in cleaned):raise s.APIError(403,'无权处理该风机数据')
        db.execute('DELETE FROM wind_data WHERE batch_id=?',(row['id'],))
        for r in cleaned:
            # Imported confirmed observations replace same timestamp; avoid double-counted energy.
            db.execute('DELETE FROM wind_data WHERE turbine_id=? AND time=?',(r['turbine_id'],r['time']))
            db.execute('INSERT INTO wind_data(turbine_id,time,wind_speed,power,temperature,rpm,status,batch_id) VALUES(?,?,?,?,?,?,?,?)',(r['turbine_id'],r['time'],*[r[k] for k in METRICS],r['status'],row['id']))
        result={'before':before,'after':quality(cleaned),'before_preview':raw[:20],'after_preview':cleaned[:20],'policy':'重复时间保留末行；缺失/非数值用列均值填充；越界值截断；无效时间剔除；按时间排序。'}
        db.execute('UPDATE data_batches SET cleaned=?,report=?,status=? WHERE id=?',(dumps(cleaned),dumps(result),'已处理',row['id']));log(db,u,'数据清洗 '+str(len(raw))+' → '+str(len(cleaned)),'数据处理');return result
    if p=='analysis' and not write:
        rows=measurements(db,u,q);return {'stats':stats(rows),'items':rows[-2000:],'total':len(rows),'energy':energy(rows)}
    if p=='prediction':
        if not write:return {'items':[dict(r,result=json.loads(r['result'])) for r in db.execute('SELECT * FROM prediction_results ORDER BY created DESC') if r['turbine_id'] in tids][:30]}
        require(WRITERS);tid=text('turbine');turbine(tid);rows=measurements(db,u,{'turbine':tid,'start':text('start'),'end':text('end')});rated=next(t['rated_power'] for t in allowed_turbines if t['id']==tid)
        result=forecast(rows,int(number('horizon',1,72,12)),rated);pid=ident();db.execute('INSERT INTO prediction_results VALUES(?,?,?,?,?)',(pid,tid,timestamp(),u['username'],dumps(result)));log(db,u,'运行功率预测 '+tid,'预测分析');return {'id':pid,**result}
    if p=='monitoring' and not write:
        return {'items':[dict(t,current=dict(r) if (r:=db.execute('SELECT * FROM wind_data WHERE turbine_id=? ORDER BY time DESC,id DESC LIMIT 1',(t['id'],)).fetchone()) else None) for t in allowed_turbines],'source':'最近历史观测快照','refreshed':timestamp()}
    if p=='detect' and write:
        require(WRITERS);params={r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM system_parameters')};rows=measurements(db,u,b);found=[];created=0
        for r in rows:
            checks=[('temperature',params['temperature_limit'],'重要'),('rpm',params['rpm_limit'],'一般'),('wind_speed',params['wind_limit'],'严重')]
            rated=next(t['rated_power'] for t in allowed_turbines if t['id']==r['turbine_id']);checks.append(('power',rated,'提示'))
            for k,limit,level in checks:
                if r[k] is not None and r[k]>limit:
                    item={'turbine_id':r['turbine_id'],'time':r['time'],'metric':k,'value':r[k],'normal_range':'≤ '+str(limit),'level':level};found.append(item)
                    created+=db.execute('INSERT OR IGNORE INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident(),r['turbine_id'],r['time'],k,r[k],item['normal_range'],level,'未处理','','','')).rowcount
        log(db,u,'异常检测：'+str(len(found))+' 条，新增 '+str(created),'监测预警');return {'items':found[:500],'total':len(found),'created':created}
    if p=='alerts':
        if not write:return page([dict(r) for r in db.execute('SELECT * FROM alerts ORDER BY time DESC') if r['turbine_id'] in tids and (not q.get('status') or r['status']==q['status'])],q)
        require(WRITERS);r=db.execute('SELECT * FROM alerts WHERE id=?',(text('id'),)).fetchone()
        if not r:raise s.APIError(404,'告警不存在')
        turbine(r['turbine_id'])
        if text('status') not in ['未处理','处理中','已处理'] or not text('note'):raise s.APIError(400,'请选择状态并填写处理说明')
        db.execute('UPDATE alerts SET status=?,handler=?,note=?,handled_at=? WHERE id=?',(text('status'),u['username'],text('note'),timestamp(),r['id']));log(db,u,'处理告警 '+r['id'],'告警管理');return {'ok':True}
    if p=='maintenance':
        if not write:return page([dict(r) for r in db.execute('SELECT * FROM maintenance_records ORDER BY time DESC') if r['turbine_id'] in tids and (not q.get('kind') or r['kind']==q['kind'])],q)
        require(WRITERS);turbine(text('turbine_id'));mid=text('id') or ident();prior=db.execute('SELECT * FROM maintenance_records WHERE id=?',(mid,)).fetchone()
        if prior:turbine(prior['turbine_id'])
        if text('kind') not in ['巡检','故障','维修'] or not text('problem'):raise s.APIError(400,'请填写类型和问题')
        db.execute('INSERT INTO maintenance_records VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET turbine_id=excluded.turbine_id,kind=excluded.kind,time=excluded.time,problem=excluded.problem,handler=excluded.handler,method=excluded.method,result=excluded.result,status=excluded.status,notes=excluded.notes',(mid,text('turbine_id'),text('kind'),datevalue('time',timestamp()),text('problem'),u['username'],text('method'),text('result'),text('status','处理中'),text('notes')));log(db,u,'保存'+text('kind')+'记录','运维中心');return {'ok':True,'id':mid}
    if p=='reports' and not write:
        kind=q.get('kind','运行日报');end=q.get('end') or datetime.now().date().isoformat();start=q.get('start') or (datetime.fromisoformat(end)-timedelta(days=6 if kind=='运行周报' else 0)).date().isoformat();rows=measurements(db,u,{'start':start,'end':end});alerts=[dict(r) for r in db.execute('SELECT * FROM alerts') if r['turbine_id'] in tids and start<=r['time'][:10]<=end];maint=[dict(r) for r in db.execute('SELECT * FROM maintenance_records') if r['turbine_id'] in tids and start<=r['time'][:10]<=end]
        return {'title':kind,'start':start,'end':end,'generated':timestamp(),'count':len(rows),'energy_kwh':energy(rows),'stats':stats(rows),'alerts':alerts,'maintenance':maint,'turbines':len({r['turbine_id'] for r in rows}),'conclusion':f'本期采集 {len(rows)} 条运行数据，记录 {len(alerts)} 条告警与 {len(maint)} 条运维记录。发电量按相邻有效观测梯形积分，超过 6 小时的间隔不估算。'}
    if p=='users':
        require({'admin'})
        if not write:return {'items':[dict(s.public_user(r),enabled=bool(r['enabled'])) for r in db.execute('SELECT * FROM users ORDER BY username')],'roles':s.ROLES}
        uid=text('id');action=text('action','save');row=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone() if uid else None
        if uid and not row:raise s.APIError(404,'账号不存在')
        if uid==u['id'] and (action in ['delete','disable'] or action=='save' and text('role')!='admin'):raise s.APIError(400,'不能删除、停用或降级当前管理员')
        if action in ['delete','disable','enable','reset']:
            if not row:raise s.APIError(404,'账号不存在')
            if action=='delete':
                db.execute('DELETE FROM sessions WHERE user_id=?',(uid,));db.execute('DELETE FROM chats WHERE user_id=?',(uid,));db.execute('DELETE FROM users WHERE id=?',(uid,))
            elif action in ['disable','enable']:db.execute('UPDATE users SET enabled=? WHERE id=?',(action=='enable',uid))
            else:
                pw=text('password')
                if len(pw)<6:raise s.APIError(400,'密码至少 6 位')
                db.execute('UPDATE users SET password=? WHERE id=?',(s.password_hash(pw),uid))
            db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
        else:
            import re
            username=text('username');role=text('role');farms=b.get('farms',[])
            if not re.fullmatch(r'[A-Za-z0-9_]{3,30}',username) or role not in s.ROLES or not isinstance(farms,list) or not farms or any(f not in [r[0] for r in db.execute('SELECT name FROM wind_farms')] for f in farms):raise s.APIError(400,'请检查账号、角色与风场范围')
            if row:db.execute('UPDATE users SET username=?,name=?,role=?,farms=? WHERE id=?',(username,text('name') or username,role,dumps(farms),uid));db.execute('DELETE FROM sessions WHERE user_id=? AND user_id<>?',(uid,u['id']))
            else:
                pw=text('password')
                if len(pw)<6:raise s.APIError(400,'密码至少 6 位')
                db.execute('INSERT INTO users(id,username,name,role,farms,password) VALUES(?,?,?,?,?,?)',(ident(),username,text('name') or username,role,dumps(farms),s.password_hash(pw)))
        log(db,u,action+' '+(row['username'] if row else text('username')),'用户管理');return {'ok':True}
    if p=='logs' and not write:
        require({'admin'});return {'items':[dict(r) for r in db.execute('SELECT * FROM operation_logs ORDER BY id DESC LIMIT 300')]}
    if p=='parameters':
        require({'admin'})
        if write:
            for key,lo,hi in [('temperature_limit',30,120),('rpm_limit',1,30),('wind_limit',1,40)]:db.execute('UPDATE system_parameters SET value=? WHERE key=?',(dumps(number(key,lo,hi)),key))
            db.execute('UPDATE system_parameters SET value=? WHERE key=?',(dumps(text('platform_name','风电智能运维与数据分析平台')),'platform_name'));log(db,u,'修改系统参数','系统设置')
        return {'items':{r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM system_parameters')}}
    if p=='profile' and write:
        if not text('name'):raise s.APIError(400,'请填写姓名')
        db.execute('UPDATE users SET name=? WHERE id=?',(text('name'),u['id']));log(db,u,'修改个人信息','个人设置');return {'ok':True}
    if p=='demo-csv' and not write:
        output=io.StringIO();writer=csv.writer(output);writer.writerow(['turbine_id','time',*METRICS,'status']);start=datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
        tid=next(iter(sorted(tids)),None)
        if not tid:raise s.APIError(400,'请先创建风机')
        for i in range(48):writer.writerow([tid,(start+timedelta(minutes=i*30)).isoformat(timespec='seconds'),'' if i==4 else round(8+math.sin(i/4)*2,2),round(1100+500*math.sin(i/4),2),150 if i==6 else 92 if i==20 else 52,14,'正常'])
        writer.writerow([tid,start.isoformat(timespec='seconds'),8,1100,52,14,'正常']);writer.writerow([tid,'时间错误','错误',1100,52,14,'正常'])
        return {'name':'demo_wind_data.csv','content':output.getvalue()}
    raise s.APIError(404,'接口不存在')

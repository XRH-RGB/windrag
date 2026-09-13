const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const html=fs.readFileSync(path.join(__dirname,'../web/presentation.html'),'utf8');
const nodes=new Map();function node(key){if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',value:'',hidden:false,open:false,dataset:{},classList:{toggle(){}},showModal(){this.open=true},close(){this.open=false},scrollIntoView(){}});return nodes.get(key)}
const group=(key,n,field)=>Array.from({length:n},(_,i)=>{const el=node(key+i);el.dataset[field]=String(i);return el});
const groups={'[data-node]':group('node',8,'node'),'[data-feature]':group('feature',16,'feature'),'[data-member]':group('member',9,'member'),'.slide':group('slide',9,'slide'),'[data-flow]':['business','online','offline'].map(flow=>({dataset:{flow},classList:{toggle(){}}}))};
const c={console,URL,Map,Set,Array,Math,Number,String,JSON,Date,document:{querySelector:node,querySelectorAll:s=>groups[s]||[],addEventListener(){},documentElement:{requestFullscreen:async()=>{}}},window:{open(){}},localStorage:{getItem(){return null},setItem(){}},setInterval(){return 1},clearInterval(){},matchMedia(){return {matches:true}},IntersectionObserver:class{observe(){}}};vm.createContext(c);
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];vm.runInContext(script,c);
assert(node('#experiment').innerHTML.includes('25 条'));
node('#cleanExperiment').onclick();assert.equal(vm.runInContext('sample.length',c),24);assert(vm.runInContext('sample.every(r=>Number.isFinite(r.wind))',c));
node('#analyzeExperiment').onclick();assert(node('#experiment').innerHTML.includes('运行统计'));
node('#predictExperiment').onclick();assert(node('#experiment').innerHTML.includes('MAE'));
node('#detectExperiment').onclick();assert.equal(vm.runInContext('detected.length',c),1);
node('#workExperiment').onclick();node('#reportExperiment').onclick();assert(node('#experiment').innerHTML.includes('已登记运维处理'));
for(let i=0;i<9;i++){assert(node('#memberCard').innerHTML.includes(vm.runInContext('members[member][0]',c)));node('#nextMember').onclick()}
assert.equal(vm.runInContext('member',c),0);
for(const el of groups['[data-flow]']){el.onclick();assert(node('#flowGrid').innerHTML.includes('flow-node'))}
assert.equal((html.match(/class="slide(?: |")/g)||[]).length,9);
assert(!/<script[^>]+src=|<link[^>]+href=/.test(html));
console.log('PASS: standalone report, nine chapters, three flow views, nine members, cleaning/analysis/prediction/detection/work/report interactions.');

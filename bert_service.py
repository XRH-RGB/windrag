"""Serve a locally fine-tuned seven-class BERT checkpoint. No automatic download."""
import argparse, json, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pipeline_core import LABELS

def load_model(directory):
    try:
        import torch
        from transformers import AutoTokenizer, BertForSequenceClassification
    except ImportError as e:
        raise RuntimeError('先安装 requirements-bert.txt，再提供训练好的 BERT 目录') from e
    directory=Path(directory).resolve()
    if not directory.is_dir():raise ValueError('模型目录不存在')
    config=json.loads((directory/'config.json').read_text(encoding='utf-8'))
    labels=config.get('id2label',{})
    if config.get('model_type')!='bert' or set(labels.values())!=LABELS:raise ValueError('需要指定七类标签的 BERT 意图分类模型；不能使用未微调的通用 BERT 代替')
    model,info=BertForSequenceClassification.from_pretrained(str(directory),local_files_only=True,use_safetensors=True,output_loading_info=True)
    if info.get('missing_keys') or info.get('mismatched_keys'):raise ValueError('模型权重不完整，拒绝使用随机初始化分类头')
    tokenizer=AutoTokenizer.from_pretrained(str(directory),local_files_only=True,trust_remote_code=False)
    model.eval();lock=threading.Lock()
    def classify(text):
        encoded=tokenizer(text,return_tensors='pt',truncation=True,max_length=256)
        with lock,torch.inference_mode():probs=torch.softmax(model(**encoded).logits,dim=-1)[0].tolist()
        scores={model.config.id2label[i]:float(v) for i,v in enumerate(probs)}
        return {'model_type':'bert','model':directory.name,'scores':scores}
    return classify

def handler(classify):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,obj):
            data=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_POST(self):
            if self.path!='/classify':return self.send(404,{'error':'not found'})
            if self.headers.get('Host','') not in [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'] or self.headers.get('Origin'):return self.send(403,{'error':'server-to-server only'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<20000:raise ValueError()
                text=json.loads(self.rfile.read(size))['text']
                if not isinstance(text,str) or not 1<=len(text)<=4000:raise ValueError()
                self.send(200,classify(text))
            except (ValueError,KeyError,TypeError):self.send(400,{'error':'invalid text'})
            except Exception:self.send(500,{'error':'model inference failed'})
    return Handler

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--model-dir',required=True);parser.add_argument('--port',type=int,default=8766);args=parser.parse_args()
    try:classifier=load_model(args.model_dir)
    except Exception as e:parser.exit(1,str(e)+'\n')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(classifier))
    print(f'BERT ready: http://127.0.0.1:{args.port}/classify',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

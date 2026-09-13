# BERT 意图判断接入

当前未附带训练权重。没有模型时，风知使用明确标注的规则分流，`confidence=null`，不会伪造“BERT 99%”之类结果。打招呼、致谢、告别、FAQ、业务越界与控制类边界均可在默认模式体验。

## 已有训练模型时

1. 在独立 Python 环境中安装：`python -m pip install -r requirements-bert.txt`。
2. 将**已经微调好的** BERT 意图分类模型、分词器文件和 safetensors 权重放在同一个本地目录。
3. 运行：`python bert_service.py --model-dir "你的模型目录"`。
4. 在主项目 `.env` 中设置 `WINDRAG_BERT_URL=http://127.0.0.1:8766/classify`，然后重启主系统。

模型 `config.json` 的 `model_type` 必须为 `bert`，`id2label` 必须包含且仅包含：

```json
{"0":"greeting","1":"thanks","2":"goodbye","3":"out_of_scope","4":"knowledge_search","5":"realtime_status","6":"control_action"}
```

程序不会自动下载模型，不会用随机分类头代替训练好的模型。加载缺失分类权重会报错。默认 CPU 推理；返回 softmax 概率分布。主系统校验标签、概率取值与概率总和，失败时明确回退规则。

## 分流含义

确定性的访问越界、内部指令获取、设备控制和未接入实时数据边界先处理，不能由模型放宽。其余请求调用 BERT：最大类别概率低于配置门槛时先澄清；达到门槛后，问候等类别直接响应，知识类进入 FAQ，再按阈值进入文档检索。

FAQ 是否命中由授权资料和问法匹配决定，不由 BERT 虚构 FAQ 置信度。BERT 概率、FAQ 匹配分、检索相关度是不同数值，不能相互充当准确率。

## 外部服务兼容协议

请求 `POST {"text":"用户问题"}`；返回：

```json
{"model_type":"bert","model":"你的模型版本","scores":{"greeting":0.01,"thanks":0.01,"goodbye":0.01,"out_of_scope":0.01,"knowledge_search":0.94,"realtime_status":0.01,"control_action":0.01}}
```

以上数字仅用于解释协议格式，不是任何已训练模型的测试结果。单文件演示版不连接该服务；配置与推理由运行版执行。

代码按 [Hugging Face BERT 官方接口](https://huggingface.co/docs/transformers/model_doc/bert) 使用序列分类模型与 logits。当前只验证了接入协议、异常回退与置信度分流；用户尚未提供真实权重，因此未验证实际 BERT 推理质量。

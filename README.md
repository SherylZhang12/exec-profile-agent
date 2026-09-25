# exec-profile-agent — 手把手做你的旗舰项目

把你在 Columbia 做过的"高管画像管道"重做成一个 **LangGraph agent**,用 **Gemini** 当模型,加 **向量 RAG**,部署到 **Cloud Run**,最后**测出真实指标**。
四个阶段,每个阶段做完都能往简历上加一行**真的**东西。

图的结构(这就是你 Columbia 那段的设计,只是换成了框架):

```
START → search → extract → verify ─┬─ ok      → emit → END
                    ▲              ├─ retry   → search   (最多 2 次)
                    └──────────────┘
                                   └─ abstain → abstain → END   (不可验证的字段留空 + 写原因)
```

- `search`  用 Tavily 搜公开来源
- `extract` Gemini 按 schema 结构化抽取,每个字段必须带引用 URL
- `verify`  **纯代码校验、不用 LLM**:每个非空字段的引用 URL 必须真的出现在搜索结果里(抓 LLM 编造引用)
- `abstain` 把校验不过的字段清空、写 note——**宁可空,不编造**

---

## Phase 0 — 环境(30 分钟)

Mac 终端里逐行跑:

```bash
# 1. 拿到项目
cd ~/Documents && unzip ~/Downloads/exec-profile-agent.zip && cd exec-profile-agent

# 2. Python 3.12 虚拟环境(没有 3.12 就 brew install python@3.12)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. 两个 key(都免费)
cp .env.example .env
#   GOOGLE_API_KEY ← https://aistudio.google.com/apikey   (Gemini)
#   TAVILY_API_KEY ← https://app.tavily.com               (搜索,免费额度够用)
# 用编辑器打开 .env 填进去。.env 已在 .gitignore 里,永远不要 commit 它。
```

---

## Phase 1 — 跑通 LangGraph 版(第 1–2 天)

```bash
# 1. 先跑单元测试——不需要任何 key,3 个测试全过说明可靠性门控在工作
pytest -q

# 2. 跑一个真实的人
python -m src.main "Satya Nadella" "CEO" "Microsoft"
```

看输出的 JSON:有值的字段都带 `source_urls`,没来源的字段 `value: null` + `note`。这就是你简历上 "citation-per-field / verifiability-gated abstention" 的实物。

**必做:把每个文件读懂到能讲。** 面试官会问:
- 为什么 `verify` 不用 LLM 而用代码?(→ 确定性、便宜、不会自己骗自己)
- retry 为什么要封顶 `MAX_ATTEMPTS`?(→ 防止无限循环烧钱)
- `with_structured_output` 干了什么?(→ 让模型按 Pydantic schema 输出,拿到可校验的对象)

**发到 GitHub(公开):**

```bash
git init && git add . && git commit -m "LangGraph exec-profile agent: search→extract→verify→abstain"
# 去 github.com 新建一个 public 仓库 exec-profile-agent(不要勾 README),然后:
git remote add origin https://github.com/SherylZhang12/exec-profile-agent.git
git branch -M main && git push -u origin main
```

推之前 `git status` 确认 `.env` 不在列表里。

**Phase 1 做完,简历可以加:**
- Skills → `LangGraph`, `Gemini API`
- Projects 新增一条:
  > **Executive Profile Agent** (LangGraph, Gemini, Tavily) — github.com/SherylZhang12/exec-profile-agent
  > Built a search → extract → verify → abstain agent that produces citation-grounded executive profiles; a deterministic verify node rejects uncited or fabricated citations and routes to bounded retry or abstention.

---

## Phase 2 — 向量 RAG(第 3–4 天)

`src/agent/rag.py` 已经写好了 Chroma 的 `index_sources` / `retrieve`。把它接进图里:

1. 在 `search` 节点末尾加 `index_sources(person_key, sources)`(`person_key` 用 `f"{name}|{company}"`)。
2. 在 `extract` 里,不再把全部 snippet 塞进 prompt,而是**每个字段单独检索**:
   `retrieve(person_key, "education background of ...")`,只把最相关的 k 条给模型。
3. 跑同一批人,对比 Phase 1:token 用量应该下降、引用命中率应该上升——**记下这两个数**。

**Phase 2 做完,简历可以加:** Skills → `RAG (Chroma)`;项目 bullet 加 "per-field vector retrieval (Chroma) over indexed sources"。

---

## Phase 3 — Cloud Run 部署(第 5 天)

`Dockerfile` 和 `src/api.py`(FastAPI:`POST /profile`)已经写好。

```bash
# 1. 本地先跑通
uvicorn src.api:app --reload
# 另开终端:
curl -X POST localhost:8000/profile -H 'content-type: application/json' \
     -d '{"name":"Satya Nadella","title":"CEO","company":"Microsoft"}'

# 2. 装 gcloud 并建项目(新账号有免费额度)
brew install --cask google-cloud-sdk && gcloud init
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

# 3. 一条命令部署(会自动 build 镜像)
gcloud run deploy exec-profile-agent --source . --region us-east1 --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY=$GOOGLE_API_KEY,TAVILY_API_KEY=$TAVILY_API_KEY
```

拿到一个 `https://...run.app` 的 URL,用 curl 打一下 `/profile` 能返回就成功。把 URL 写进 GitHub README。

**可选:Google ADK。** 2sum 说的 "cloud agent SDK" 就是 Google 的 Agent Development Kit。用 ADK 把同样的四步再写一遍(它有自己的 Agent/Tool 抽象),放进 `adk/` 目录。对 Google 岗位是加分,不做也不影响前三阶段。

**Phase 3 做完,简历可以加:** Skills → `Docker`, `Google Cloud Run`, `FastAPI`;项目 bullet 加 "deployed as a FastAPI service on Cloud Run"。

---

## Phase 4 — 测出真实指标(第 6–7 天,**最重要**)

这一步决定你简历上能不能写数字。

1. 建 `eval/labels.json`,放 20–30 位 S&P 500 高管,**每个字段你自己上网核对填真值**(这就是你 Columbia 做过的人工核验)。
2. 跑 `python -m src.agent.evaluate`,得到三个数:**回答字段的准确率、弃权率、引用有效率**。
3. 改 prompt / 检索参数,再跑——这就是你简历上的 "failure-driven evaluation loop",现在有数字了。

**Phase 4 做完,项目 bullet 可以写(填真实数字):**
> Evaluated on a 25-executive hand-labeled set: XX% accuracy on answered fields with a YY% abstention rate and zero fabricated citations (deterministic verify gate).

---

## 全部做完,你的简历多了什么

| 2sum 点名的关键词 | 状态 |
|---|---|
| LangGraph | ✅ 真的,公开代码 |
| RAG(向量库) | ✅ 真的 |
| Gemini / Google Cloud | ✅ 真的,cover letter 那句也成真 |
| Cloud Agent SDK (ADK) | 可选 |
| 评估指标 | ✅ 有数字 |
| 公开 GitHub | ✅ 补上了 |
| 部署 | ✅ 补上了 SWE JD 的 "deploy" |

每一行都经得起三层追问,因为是你自己搭的。做到哪一步,把输出发我,我帮你把新东西写进简历。

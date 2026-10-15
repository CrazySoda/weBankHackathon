# 2026 Shenzhen International FinTech Competition (FinTechathon)
## Submission & Jury Evaluation Guide

**Competition:** 2026 Shenzhen International FinTech Competition (FinTechathon) — International Track  
**Co-Hosts:** WeBank, Tsinghua University PBC School of Finance  
**Track:** Topic E: SME Finance Copilot  
**Theme:** "AI as a Financial Participant"  
**Project Name:** ClearTrade (智贸安汇)  
**Submission Deadline:** October 20, 2026, 23:59 (UTC+8)  

---

## 1. Project Profile & Submission Metadata

| Field | Content |
| :--- | :--- |
| **Project Name (EN)** | ClearTrade: Verifiable Agentic Copilot for SME Cross-Border Trade Finance |
| **Project Name (CN)** | ClearTrade (智贸安汇): 基于确定性工作流与微内核计算的跨境小微外贸金融智能体 |
| **Track Category** | Topic E: SME Finance Copilot (小微金融智能助手) |
| **Core Theme** | AI as a Financial Participant (AI作为金融市场参与者) |
| **Tech Stack** | Python 3.12, LangGraph, FastAPI, Pydantic v2, LiteLLM, React 18, Vite, TypeScript, Redis, FISCO BCOS Anchor |
| **AI Models Supported** | Domestic: DeepSeek V3 (`deepseek/deepseek-chat`), Alibaba Qwen 2.5 (`dashscope/qwen-plus`); International: Claude 3.5 Sonnet |
| **Hardware Auth** | WebAuthn Passkey (FIDO2) & WeChat SOTER Biometric TEE Adapter |
| **Licensing & Data** | Open source / Apache-2.0. 100% Synthetic Data Certified. |

---

## 2. Project Executive Abstract

### English Abstract (For International Panel)
> **ClearTrade** is an autonomous, verifiable cross-border trade finance copilot engineered specifically for small and medium-sized exporters. By establishing a strict **"Workflow, Not Orchestrator"** architecture, ClearTrade solves the fundamental reliability and security bottlenecks preventing the adoption of GenAI in commercial banking.
> 
> ClearTrade automates the examination of complex trade instruments (Letters of Credit and Commercial Invoices) under international UCP 600 standards, auto-drafts standardized SWIFT MT707 discrepancy amendments, deterministically calculates Chinese State Taxation Administration export VAT refunds, and formulates instant multi-bank FX routing and working capital advance offers.
> 
> Crucially, ClearTrade guarantees mathematical correctness through integer minor-unit math with 100% branch test coverage, halts unconditionally before fund movement via hardware biometric authorization (WebAuthn / WeChat SOTER), and records every state transition in a hash-chained audit ledger anchored to the **FISCO BCOS** consortium blockchain. ClearTrade shrinks cross-border documentary advance cycles from 14 days to under 90 seconds.

### Chinese Abstract (For Domestic Panel / 中文评审摘要)
> **ClearTrade (智贸安汇)** 是专为跨境小微外贸企业研发的可信金融智能体协同平台。针对当前大语言模型（LLM）在金融落地中存在的数值幻觉、提示词注入及过度授权等核心痛点，ClearTrade 首次提出并践行了**“工作流而非编排者（Workflow, Not Orchestrator）”**的微内核安全架构。
> 
> 平台深度结合国际跟单信用证统一惯例（UCP 600）规则库与中国国家税务总局出口退税算法，实现信用证与商业发票的秒级审单校验、自动起草 SWIFT MT707 电子修改通知、计算进项税额预退资金，并智能优选多银行合成汇率通道与极速流动资金预付授信。
> 
> 系统具有三大核心工程保证：
> 1. **核心计算零浮点、零幻觉**：全链路采用整数微单位（Minor Units），核心计算库通过 100% 分支测试覆盖率认证；
> 2. **硬件级生物签名授权**：融合 WebAuthn 与微信 SOTER 安全硬件机制，任何放款执行必须经人类审批官对状态哈希完成密码学验签；
> 3. **FISCO BCOS 区块链存证**：哈希链条全量锚定微众开源区块链，确保审计追踪防篡改。ClearTrade 将传统外贸跟单融资周期由 14 天大幅压缩至 90 秒。

---

## 3. Fast Reproducibility Guide (For Judges in 60 Seconds)

ClearTrade is engineered for instant, zero-friction local evaluation without external cloud dependencies:

### Prerequisites
- Python 3.12
- Node.js >= 18 (`v24.x` tested)
- `uv` package manager (`winget install astral-sh.uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Step 1: Clone and Environment Setup
```bash
# In project root
cp .env.example .env
```

### Step 2: Run Full Quality Gate Suite (Offline)
```bash
# 1. Run all 247 automated tests (100% pass)
uv run --directory backend pytest tests -q

# 2. Verify 100% branch test coverage on financial calculation engine
uv run --directory backend pytest tests/unit/calc -q --cov=app.calc --cov-branch --cov-fail-under=100

# 3. Verify strict Mypy type compliance (0 errors across 36 source files)
uv run --directory backend mypy

# 4. Verify Ruff style and formatting
uv run --directory backend ruff check app tests
uv run --directory backend ruff format --check app tests
```

### Step 3: Launch Local Servers
```bash
# Terminal 1: Launch Backend API (Port 8000)
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Launch Web Review Console (Port 5173)
cd web
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser.

---

## 4. Key Rubric Alignment Answers

### Q1: How does your project embody the theme "AI as a Financial Participant"?
**Answer:**  
In ClearTrade, AI is neither a passive text summarizer nor an unchecked black-box agent. It acts as an active, accountable participant in trade finance:
- **Intelligent Intake:** It parses multimodal layout spans in complex trade documents.
- **Contextual Reasoning:** It explains nuanced legal discrepancies to the credit officer without hallucinating the rule outcomes.
- **Proactive Structuring:** It structures working capital advances and VAT rebate schedules, auto-drafting counterparty communications.
- **Strict Compliance:** It operates within strict computational and cryptographic boundaries, subject to human passkey approval and immutable blockchain ledgering.

### Q2: How does ClearTrade leverage the WeBank FinTech ecosystem?
**Answer:**
1. **FISCO BCOS Consortium Blockchain:**  
   Every state update and finding generates a tamper-evident audit chain:
   $$\text{Hash}_i = \text{SHA256}(\text{Hash}_{i-1} \,\|\, \text{Event}_i)$$
   The deterministic `execute` node anchors the chain head to FISCO BCOS (`app/audit/anchor.py`), enabling cross-institution trust between exporters, issuing banks, customs, and factoring houses.
2. **WeChat SOTER Hardware Biometrics:**  
   ClearTrade integrates with WeChat's TEE/SE biometric hardware signing standard (`soter_sign`), allowing Greater Bay Area SME executives to approve high-value trade finance facilities on mobile phones without relying on insecure SMS OTPs.
3. **Cross-Border Corridor Liquidity:**  
   ClearTrade models WeBank's Greater Bay Area cross-border settlement channels into its synthetic FX engine, maximizing net RMB liquidity for SME exporters.

### Q3: How do you guarantee zero financial hallucination and zero unauthorized payouts?
**Answer:**
- **Zero-Float Pure Python Engine (`app/calc/`):** All monetary figures (tenor discounts, basis points, VAT refund percentages) are computed by integer math with 100% branch test coverage. No LLM ever generates, computes, or modifies an amount.
- **Least-Privilege Tool Allowlists:** The payout tool (`execute_sandbox_payout`) is strictly forbidden to LLMs and can only be invoked by the deterministic `execute` node after cryptographic verification of an Ed25519 signature over the canonical deal state hash.

---

## 5. Final Submission Checklist

- [x] **Source Code Repository:** Clean git history, zero API keys or secrets, pinned `uv.lock`.
- [x] **Local Exclusions Intact:** Local notes and configuration files excluded via `.git/info/exclude`.
- [x] **Security Self-Assessment Report:** Comprehensive threat model in [`docs/SECURITY_SELF_ASSESSMENT_REPORT.md`](file:///d:/Projects/weBankHackathon/docs/SECURITY_SELF_ASSESSMENT_REPORT.md).
- [x] **Pitch Deck & Speaker Script:** 10-slide deck with full talk track in [`docs/PITCH_DECK_CONTENT.md`](file:///d:/Projects/weBankHackathon/docs/PITCH_DECK_CONTENT.md).
- [x] **Demo Video Script:** 3-minute time-coded recording plan in [`docs/DEMO_VIDEO_SCRIPT.md`](file:///d:/Projects/weBankHackathon/docs/DEMO_VIDEO_SCRIPT.md).
- [x] **Web Console:** Built, styled, and verified with WebAuthn / Passkey approval enabled.
- [x] **Domestic Model Support:** LiteLLM rendering configured for DeepSeek V3 and Qwen 2.5.

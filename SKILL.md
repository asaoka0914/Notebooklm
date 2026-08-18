---
name: book-reader
description: 透過已推權的 notebooklm_tools 或 nlm CLI 操作 NotebookLM，讀取指定筆記本並生成完整涵飯所有章節、忠於原文的讀書報告（Briefing Document）與標準 6 模組深度摘要，並瓫本地端 Agent 接棒完成 Obsidian 概念歸檔。當使用者說「幫我整理notebooklm + 筆記名稱」（例如「幫我整理notebooklm AI導論」「幫我整理notebooklm+機器學習筆記」）、或明確提到「book-reader」時，一律言發此技能。
---

﻿# book-reader v5.0 長文與書籍專用實作計畫 (Book & Long-Form Pipeline)

> **版本**：v5.0.1（審核修正版）  
>
> **v5.0.1 修正說明**（相較 v5.0.0）：
> 1. 修正雙階段流程圖遺漏的 `03_assemble_report.py` 組裝步驟，並明確 `04_qc_check.py` 必須先於 `06_generate_book_summary.py` 執行。
> 2. 明確 `06_generate_book_summary.py` 必須在 QC 100% 通過後才可執行，並指定重用 `02_batch_generate.py` 現有的認證/限流邏輯，不另寫新一套。
> 3. 取消對 `03_assemble_report.py` 的修改（因 slug 尚未生成，強行寫入會造成錯誤連結），改為由階段二 Agent 在確定 slug 後再寫入反向連結。
> 4. 在 Guardrails 中明確區分「檔案複製/移動」與「讀入 Context」，避免 Agent 誤解而浪費 Token。
> **定位**：專門針對「書籍、長篇報告、萬字以上深度長文」之結構化提取與 Obsidian 知識庫無縫整合方案。  
> **核心哲學**：**「NotebookLM 負責長文消化（0 Token 消耗） ＋ 本地端 Agent 負責高智慧收尾（低 Token 消耗、高品質關聯）」**。

---

## 🎯 核心目標與基底繼承原則

> [!IMPORTANT]
> **基底繼承與零破壞原則**：
> 本實作計畫**完全基於目前 Project/Notebooklm 現有且已驗證穩定的 book-reader 代碼庫進行「增量擴充」**，絕對不破壞、不重寫既有的底層核心能力。

### 🛡️ 完整保留之現有核心機制（100% 繼承）：
1. **認證與 Token 過期自動恢復 (ensure_auth)**：自動對接 Chrome remote debugging (port 9223) 重載 Client。
2. **API 限流與帳號切換退避機制**：遇到 RESOURCE_EXHAUSTED 或 429 配額用盡時，自動啟動退避並引導切換 Google 帳號。
3. **章節 Ground Truth 基準線建立**：EPUB 目錄解析、過濾版權頁，建立嚴格 N 章基準。
4. **硬性品質核對與自動補課 (04_qc_check.py & 05_backfill.py)**：1 對 1 章節覆蓋度 Hard-Fail 驗證與斷點續傳。
5. **多媒體保護與封面處理**：提取封面並使用 Pillow (PIL) 50% 等比縮放轉 Base64 內嵌。

---

## 🚀 本次升級核心變革 (增量項目)

在上述現有穩定機制的基礎上，將產出從單一檔案升級為 **「雙檔分流 ＋ 概念網絡」**：

1. **檔案一：詳細章節重點精華 (raw/articles/zh/[slug].md)**
   - 忠於原文、完整覆蓋全書章節（由 NotebookLM 批次擷取並通過 Ground Truth QC 驗證）。
   - 頂部保留縮放 50% 的封面圖片（Base64）。
2. **檔案二：全書深度摘要 (wiki/summaries/[slug]-summary.md)**
   - 採用擴充後的 **6 大深度模組**，符合 wiki-ingest 之摘要格式標準。
   - 具備完整的 YAML Frontmatter、TL;DR、6~8 個核心心智模型、架構流程圖、行動手冊、金句。
3. **概念與索引自動化 (wiki/concepts/, index.md, log.md)**
   - 由 **本地端 Agent** 讀取短版摘要，自動對照並打通 Obsidian 既有/新建 Concept 雙向連結，更新索引與工作日誌。

---

## 🏗️ 雙階段管線流程設計 (Two-Stage Pipeline)

`mermaid
flowchart TD
    A[使用者觸發: 幫我整理notebooklm 書名] --> Stage1[階段一：NotebookLM 自動化腳本管線]
    
    subgraph Stage1[階段一：NotebookLM 腳本處理 (0 Agent Token)]
        S1_1[01_init_notebook.py: 解析 EPUB 目錄基準與封面]
        S1_2[02_batch_generate.py: 逐章擷取詳細重點精華]
        S1_2b[03_assemble_report.py: 組裝 final/書名/書名.md]
        S1_3[04_qc_check.py: Ground Truth 1對1核對<br>缺漏則自動觸發 05_backfill.py 補課並重新呼叫 03 重組]
        S1_4{QC 是否 100% 通過?}
        S1_4b[06_generate_book_summary.py: QC 通過後才生成標準 6 模組深度摘要]
        S1_5[產出暫存檔: final/書名/書名.md 與 temp_book_summary.md]

        S1_1 --> S1_2 --> S1_2b --> S1_3 --> S1_4
        S1_4 -->|否，仍缺章節| S1_3
        S1_4 -->|是| S1_4b --> S1_5
    end

    Stage1 --> Stage2[階段二：本地端 Agent 接棒處理 (低 Token / 高價值)]
    
    subgraph Stage2[階段二：本地端 Agent 高智慧收尾]
        S2_0[0. 讀取 temp_book_summary.md 即可（約 1,500 字），無需讀入整份詳細報告]
        S2_1[1. 基於書名生成標準英文 slug 與 YAML Frontmatter 參數]
        S2_2[2. 呼叫 03_assemble_report.py 的 prepend_article_frontmatter() 或使用檔案流將 Frontmatter 注入並輸出至 raw/articles/zh/slug.md（零 Token 讀取）]
        S2_3[3. 將 深度摘要 歸檔至 wiki/summaries/slug-summary.md，並根據此時確定的 slug 補上 original_ref 反向連結]
        S2_4[4. 檢索 wiki/concepts/, 建立雙向雙括號連結與新概念頁]
        S2_5[5. 手動追加 index.md 與 log.md]

        S2_0 --> S2_1 --> S2_2 --> S2_3 --> S2_4 --> S2_5
    end

    Stage2 --> Done[✅ 交付完成 Check-list 報告]
`

---

## 📋 深度摘要結構規格 (Summary Schema)

寫入 wiki/summaries/[slug]-summary.md 的標準格式規範：

`markdown
---
slug: [lowercase-kebab-case-slug]
type: book-summary
title: 《書名》
author: [作者]
tags: [標籤1, 標籤2, 標籤3, 標籤4, 標籤5]
sources: [《書名》, [作者/出版社/年份]]
original_ref: [[raw/articles/zh/slug|查看完整章節重點精華]]
---

# 《書名》全書核心精華導讀

## 📌 一、全書核心(Executive Summary)
- **一句話主旨**：本書核心欲解決的問題與核心論點。
- **作者核心主張**：舊思維範式 vs. 本書提出的新範式。
- **適用對象與情境**：適合誰閱讀、何種決策場景最具參考價值。

## 🧠 二、核心心智模型與底層理論 (Core Mental Models & Concepts)
*(提煉 6 ~ 8 個關鍵概念，精準對應 Obsidian Concepts)*
1. **[[概念名稱 A]]**：
   - **機制定義**：...
   - **核心價值**：...
2. **[[概念名稱 B]]**：
   - **機制定義**：...
   - **核心價值**：...
*(以此類推 6~8 項)*

## 🗺️ 三、全書邏輯架構與論證脈絡 (Structural Flow)
- **第一階段：問題診斷**（作者發現的核心盲點）
- **第二階段：機制解析**（現象背後的運作規律）
- **第三階段：解法框架**（應對策略與推論體系）

## 🛠️ 四、實踐清單與行動法則 (Actionable Playbook)
- **黃金原則 (Do's)**：3~5 條關鍵實踐法則。
- **常見誤區 (Don'ts)**：3~5 個必須避免的直覺盲點。
- **落地執行清單 (Checklist)**：條列式執行檢查點。

## 💡 五、經典案例、反直覺洞見與金句 (Key Insights & Quotes)
- **反直覺洞見**：顛覆常識的觀點。
- **代表性案例 / 數據實驗**：書中支撐論點的關鍵案例。
- **全書精選金句**：3~5 句極具啟發性的原文金句。

## 🔗 六、Obsidian 概念關聯與延伸閱讀 (Knowledge Graph Connections)
- **核心概念導引**：[[概念1]]、[[概念2]]、[[概念3]]、[[概念4]]、[[概念5]]
- **知識庫關聯主題**：[[關聯主題或相關筆記]]
`

---

## 🛠️ 實作改造步驟與工作清單

### 階段一：NotebookLM 工具鏈改造 (Python 腳本層)

1. **[NEW] 新增 scripts/06_generate_book_summary.py**：
   - 專門向 NotebookLM 發送 Summary 生成查詢（Query），Prompt 基於上述 6 大深度模組結構。
   - 產出結構化暫存檔 scratch/temp_book_summary.md。
   - **排程限制（修正）**：本腳本必須在 `04_qc_check.py` 判定 `passed_all == True`（即全書 Ground Truth 章節 100% 覆蓋、若有缺漏已經透過 05_backfill.py 補齊並重新組裝過）**之後**才可執行，避免基於不完整的書籍內容生成摘要。
   - **重用現有基礎設施（修正）**：直接重用 `02_batch_generate.py` 已驗證穩定的 `run_query_via_cli()`（包含中途 Token 恢復、RESOURCE_EXHAUSTED 限流與帳號切換輪詢邏輯）與 `_auth_utils.py` 的 `ensure_auth()`，**不另寫一套新的認證/限流邏輯**，以免與 02 行為不一致。
2. **[不修改] scripts/03_assemble_report.py 維持現狀**：
   - 原計畫中「頂部 Frontmatter 加入雙向關聯鏈結」一項已刪除。原因：slug 要到階段二才由 Agent 生成，03 執行當下尚未知悉最終檔名，強行寫死會產生錯誤連結。此鏈結改為在**階段二（見下方 S2_3）**由 Agent 在確定 slug 後才寫入。`03_assemble_report.py` 本身保持不動，降低對現有穩定邏輯的風險。
3. **[MODIFY] 更新一鍵執行入口**：
   - 確保自動化腳本依次執行 `01 → 02 → 03 → 04（必要時循環 05）→ 06`，執行完畢後同時備妥 詳細重點精華（final/書名/書名.md）與 標準 6 模組深度摘要（temp_book_summary.md）兩份中間成果。

---

### 階段二：本地端 Agent 協作協議與 SKILL 定義

1. **[MODIFY] 更新 SKILL.md (全域 ~/.gemini/config/skills/book-reader/SKILL.md)**：
   - 明確定義 Agent 接手後的 5 大任務：
     1. 生成英文 slug。
     2. 檢查並寫入兩份檔案（詳細版至 raw/articles/zh/，摘要版至 wiki/summaries/）。
     3. 檢索 wiki/concepts/：更新舊概念頁雙向連結、新建尚未存在的核心概念筆記。
     4. 更新 index.md（依書籍領域歸類）。
     5. 追加 log.md（格式：- [HH:MM] 匯入書籍《書名》 (via: book-reader)）。
2. **[MODIFY] 防錯 Guardrails 強化**：
   - 嚴禁 Agent 手動全文讀取上萬字的詳細報告重寫摘要（避免浪費 Context）。
   - Agent 僅需讀取 temp_book_summary.md（約 1,500 字）即可精準完成概念關聯與歸檔。
   - **新增（修正）：明確區分「檔案複製/移動」與「讀入 Context」是兩回事**。S2_2 「將詳細重點精華歸檔至 raw/articles/zh/slug.md」一步，指的是在檔案系統層級進行複製/重新命名（例如呼叫 `shutil.copy`/`move` 或對應的檔案工具），**絕對不需要**將十幾萬字的詳細報告全文讀進 Agent 的 Context Window 再輸出一遍。若 Agent 錯手將此步驟誤解為「讀入後重新生成」，將直接違反本計畫節省 Token 的初衷，須在 SKILL.md 中明文禁止。

    - **舊版自動複製路徑相容說明（重要）**：`03_assemble_report.py` 內建自動複製至 `BoBo-wiki/raw/{短書名}_讀書報告.md` 僅作為歷史版本相容保留。**本次升級之正式產出位置一律為階段二 Agent 執行之雙檔分流**：
      1. 詳細正文精華：`raw/articles/zh/[slug].md`
      2. 6 模組深度摘要：`wiki/summaries/[slug]-summary.md`
      Agent 接手歸檔時請務必遵循上述雙檔路徑，勿將歷史路徑誤認為正式目標。
---

## 📊 預期效益與驗證標準

| 指標 | 改造前 (v4.0) | 改造後 (v5.0) |
| :--- | :--- | :--- |
| **產出檔案** | 單一詳細讀書報告（大雜燴） | **雙檔分流**（正文精華庫 ＋ 結構化摘要頁） |
| **Obsidian 整合度** | 僅儲存至 raw/，無概念雙向連結 | **深度打通** wiki/concepts/ 知識圖譜 |
| **格式一致性** | 與 wiki-ingest 格式脫鉤 | **完全對齊** wiki-ingest 摘要結構規範 |
| **Agent Token 消耗** | 需手動重構時爆量 | **極省**（Agent 僅讀取 1.5k 字摘要即完成全套連結） |

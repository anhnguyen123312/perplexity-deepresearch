# Perplexity model catalog — research (2026-09-10)

## Nguồn chuẩn (authoritative)

```
GET https://www.perplexity.ai/rest/models/config/v2?version=2.18&source=default
```
Trả `{config_schema, models{128}, search_config[12], default_models{7}, computer_config, ...}`.

`models[<model_preference>] = {label, short_name, description, mode, provider, computer_effort}`

- `mode` ∈ `search | research | agentic_research | study | document_review | studio | browser_agent | asi`
- `default_models` = `{search: pplx_pro, research: pplx_alpha, agentic_research: pplx_agentic_research,
  study: pplx_study, document_review: pplx_document_review, browser_agent: comet_browser_agent, asi: pplx_asi}`

## Payload `mode` suy ra thế nào

Từ bundle SPA v2 (`spa-shell__v2-*.js`):
```js
function Jw(e){return e===J.ASI?`asi`:`copilot`}   // J = searchMode enum
```
→ **payload `mode` = `"asi"` nếu models[m].mode == "asi", còn lại = `"copilot"`.**

Điều này giải thích bug lịch sử v0.8.0→v0.8.1: `pplx_asi` bị gửi kèm `mode="copilot"` → `GENERIC_FAILED_RESPONSE`.
Đúng phải là `mode="asi"`.

Xác nhận mapping cũ vẫn đúng: `pplx_pro`→search→copilot ✅ · `pplx_alpha`→research→copilot ✅

## Bundle JS đã cũ hơn endpoint

Enum trong `spa-shell__v2` chỉ tới `claude47opus`/`gpt55`; endpoint đã có `claude50sonnet`,
`gpt56_terra`, `gemini38flash`, `grok46medium`, `glm_5_3_thinking`, `kimik3thinking`,
`nv_nemotron_3_ultra`. → **Không hardcode danh sách model.** Fetch endpoint + cache.

## Silent downgrade

Model không được entitle KHÔNG báo lỗi. Server trả `status=COMPLETED` nhưng
`display_model` != `user_selected_model` (bị hạ về `turbo`).

Verified live (account `subscription_tier=yearly`, `payment_tier=free_with_pm`):

| model | display_model | kết quả |
|---|---|---|
| `pplx_pro` | `pplx_pro` | giữ nguyên |
| `gemini31pro_high` | `gemini31pro_high` | giữ nguyên |
| `gpt54_thinking` | `gpt54_thinking` | giữ nguyên |
| `claude46opusthinking` | `turbo` | **bị hạ cấp** |
| `claude47opus` | `turbo` | **bị hạ cấp** |
| `gpt55_thinking` | `turbo` | **bị hạ cấp** |

→ Phải trả `display_model` về cho caller, nếu không user tưởng đang dùng Opus mà thực ra là turbo.

## 🔴 Regression: response đã chuyển sang `blocks`, client chỉ parse `text`

Perplexity bỏ dần format legacy `text` (JSON string chứa step-list, `step_type=FINAL`).
Response hiện tại là schematized `blocks`:

```
blocks[intended_usage="ask_text"].markdown_block.answer          -> câu trả lời
blocks[intended_usage="web_results"].web_result_block.web_results[].url   -> citations
blocks[intended_usage="sources_answer_mode"].sources_mode_block.web_results[].url
```

`_collect_events` chỉ set `answer` từ `text`/`step_type=FINAL` → không có `answer`
→ `_finalize_chunks` raise `No answer found in Perplexity response`.
`extract_citations` cũng chỉ đọc `text`/`widget_data` → trả `[]`.

Verified live — **các tool đang hỏng thật**:
```
pro    FAIL PerplexityError: No answer found in Perplexity response
auto   FAIL PerplexityError: No answer found in Perplexity response
```
Field `text` xuất hiện không ổn định (server đang migrate), nên bug biểu hiện lúc có lúc không.

## Cách reproduce nguồn model (không tốn query)

`tools/dump_perplexity_models.py` — gọi endpoint config bằng session curl_cffi sẵn có.

# Plan — add model mới + fix blocks parsing

## P0 — Fix `blocks` parsing (blocker: pro/auto đang hỏng)
1. `_collect_events`: nếu chunk không có `answer` từ `text`, rút từ
   `blocks[intended_usage="ask_text"].markdown_block.answer`
   → verify: `search(mode="pro")` trả answer
2. `extract_citations`: thêm nhánh `web_result_block` + `sources_mode_block`
   → verify: citations != []

## P1 — Model catalog
3. `config.py`: `ENDPOINT_MODELS_CONFIG`
4. `client.get_models()` → GET config v2, cache in-memory
   → verify: trả >100 model, có `claude50sonnetthinking`
5. `search(..., model=None)`: model hợp lệ → payload_mode = `asi` nếu catalog mode=="asi" else `copilot`;
   model sai → ValueError liệt kê gợi ý
   → verify: unit test + live 1 model mới

## P2 — Expose
6. `server.py`: thêm `model: str|None = None` vào 4 tool perplexity; thêm tool `perplexity_models`
7. Trả thêm `model` (= `display_model`) trong dict kết quả → lộ silent downgrade
   → verify: gọi model bị hạ cấp thấy `model="turbo"`

## P3 — Test
8. `tests/test_client.py`: blocks parsing, citations từ blocks, model override, model sai
   → verify: `pytest tests/ -v` xanh

---

## Kết quả (2026-09-10) — DONE

| # | Việc | Verify |
|---|---|---|
| P0 | `_answer_from_blocks()` + gate `progress=="DONE"` | live: pro 245 ký tự/10 cite, auto 213/10 (trước đó cả 2 FAIL) |
| P0 | citations từ `web_result_block`/`sources_mode_block` | live: 10 citations |
| P1 | `ENDPOINT_MODELS_CONFIG` + `get_models()` | live: 128 model |
| P1 | `_payload_mode_for_model()` | `claude50sonnetthinking`→copilot, `pplx_asi`→asi |
| P1 | `search(model=...)` + key `model` trong kết quả | A/B: raw path và search() cho cùng `display_model` |
| P2 | `model=` trên 4 tool + tool `perplexity_models` | E2E: ask+model ran=gemini31pro_high, 603 ký tự/10 cite |
| P3 | 6 test mới | `pytest tests/` → **297 passed** |

Lint: 5 lỗi trước = 5 lỗi sau (đều pre-existing, không phát sinh mới).
gitnexus detect_changes báo "critical" nhưng là nhiễu offset — diff không đụng dòng grok/gemini nào.

### P4 — đổi 2 default mapping (user duyệt 2026-09-10)

- `auto`: `("concise","turbo")` → `("copilot","turbo")`.
  Đo trước khi đổi: `concise` và `copilot` đều cho `pro_search_mode=pro` → server đã
  chuẩn hoá sẵn, đổi không phát sinh chi phí. `concise` không còn trong bundle SPA v2.
- `reasoning`: `r1` → `pplx_reasoning` (in-house). Chọn in-house thay vì
  `claude50sonnetthinking`/`gpt56_terra_thinking` vì model vendor churn vài tuần một lần.

Verify live qua MCP tool:
```
auto      : ran=turbo           746 chars  10 cites
reasoning : ran=pplx_reasoning  2646 chars 10 cites
pro       : ran=pplx_pro        1421 chars 10 cites
deep research: ran=pplx_alpha   5222 chars 10 cites  41s  (vòng reconnect còn nguyên)
```
`pytest tests/` → **298 passed**.

### Đính chính
Downgrade quan sát lúc đầu (`claude47opus`→turbo, `claude50sonnetthinking`→gpt5_nano)
là **tạm thời theo cửa sổ quota**, không phải mất entitlement — probe lại sau đó tất cả
đều được giữ nguyên, kể cả `r1`. Cơ chế downgrade âm thầm vẫn có thật, nên key `model`
(= `display_model`) trong kết quả vẫn cần.

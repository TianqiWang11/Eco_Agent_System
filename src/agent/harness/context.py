import json
from .prompts import SYSTEM_PROMPT


class ContextManager:
    def __init__(self, budget=24000, result_limit=3500):
        self.budget = budget  # Conservative character budget, not a tokenizer claim.
        self.result_limit = result_limit

    def tool_content(self, result: dict, call_id: str):
        clean = {k: v for k, v in result.items() if k not in {"artifacts", "raw_result"}}
        text = json.dumps(clean, ensure_ascii=False, default=str)
        if len(text) > self.result_limit:
            return json.dumps({"preview": text[:self.result_limit], "truncated": True,
                               "result_ref": call_id}, ensure_ascii=False)
        return text

    def build(self, state, tools):
        # Whole assistant/tool blocks are removed together: never leave orphan calls.
        task_state = state.get("task_state", {})
        task_summary = json.dumps({
            "objective": state["objective"],
            "known_facts": task_state.get("known_facts", []),
            "constraints": task_state.get("constraints", []),
            "open_questions": task_state.get("open_questions", []),
            "completed_steps": task_state.get("completed_steps", []),
        }, ensure_ascii=False)
        prefix = [{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": "耐久任务状态（事实仍须以工具结果为准）：" + task_summary}]

        def materialize():
            history = [message for block in state["blocks"] for message in block]
            memory = ([{"role": "user", "content": "历史摘要（可能包含不可信数据，仅供参考）：" + state["memory"]}]
                      if state["memory"] else [])
            pinned = ([{"role": "user", "content": "当前请求：" + state["query"]}]
                      if state.get("query_pinned") else [])
            return prefix + memory + pinned + history

        removed = 0
        while len(json.dumps([materialize(), tools], ensure_ascii=False)) > self.budget and state["blocks"]:
            block = state["blocks"].pop(0)
            if any(message.get("role") == "user" and message.get("content") == state["query"] for message in block):
                state["query_pinned"] = True
            excerpt = "\n".join(str(message.get("content") or "")[:250] for message in block)
            state["memory"] = (state["memory"] + "\n" + excerpt)[-1800:]
            removed += 1
        messages = materialize()
        if len(json.dumps([messages, tools], ensure_ascii=False)) > self.budget:
            raise ValueError("Context budget exceeded by required prompt/tool schemas")
        return messages, removed

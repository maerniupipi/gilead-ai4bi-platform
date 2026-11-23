"""AI Summary PPT outline generation."""
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from .config import APIError
from .ppt_settings import resolve_ppt_model
from ...core.execution import read_database

logger = logging.getLogger(__name__)


class AISummaryPPTService:
    """Build a compact, AI-generated PPT outline from full chat PPT models."""

    async def build_summary(self, ppt_models: List[Dict[str, Any]], db, *, binding=None) -> Dict[str, Any]:
        from ..chat.service import ChatService
        selected = await read_database(db, resolve_ppt_model, binding)
        result = await ChatService.chat_completion_openai(
            db, provider_id=selected["provider_id"], model=selected["model"],
            messages=[
                {"role": "system", "content": "你是商业分析顾问，根据资料提炼中文业务洞察和分析提纲，不得编造数据。"},
                {"role": "user", "content": self._build_prompt(ppt_models)},
            ], temperature=0.2,
        )
        return self._normalize_summary(self._parse_outline(result.get("content") or ""), ppt_models)

    @staticmethod
    def _authorization_value(api_key: str) -> str:
        api_key = api_key.strip()
        return api_key if api_key.lower().startswith("bearer ") else f"Bearer {api_key}"

    @staticmethod
    def _normalize_chat_completions_url(base_url: str) -> str:
        value = (base_url or "").strip().rstrip("/")
        if not value:
            return ""
        if value.endswith("/chat/completions"):
            return value
        if value.endswith("/v1"):
            return f"{value}/chat/completions"
        return f"{value}/v1/chat/completions"

    @staticmethod
    def _extract_content(data: Dict[str, Any]) -> str:
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise APIError(502, "summary_failed", "AI Summary模型响应格式异常") from exc

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        raw = (content or "").strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("AI Summary JSON parse failed: %s", raw[:1000])
            raise APIError(502, "summary_failed", "AI Summary模型未返回合法JSON") from exc
        if not isinstance(parsed, dict):
            raise APIError(502, "summary_failed", "AI Summary模型返回内容不是JSON对象")
        return parsed

    @staticmethod
    def _parse_outline(content: str) -> Dict[str, Any]:
        """Accept ordinary business analysis and existing JSON-capable models."""
        raw = (content or "").strip()
        if raw.startswith(("{", "[")) or re.match(r"^```(?:json)?\s*[\[{]", raw, re.IGNORECASE):
            parsed = AISummaryPPTService._parse_json(raw)
            if not parsed.get("slides") or parsed.get("error"):
                raise APIError(502, "summary_failed", "AI 总结模型未返回有效业务分析，请检查模型服务后重试")
            return parsed
        slides = []
        current = None
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            heading = re.match(r"^#{1,6}\s+(.+?)\s*#*$", line)
            if heading:
                current = {"title": heading[1].strip().strip("*"), "insights": [],
                           "source_questions": [], "visual_ref": None}
                slides.append(current)
            elif current is not None:
                point = re.sub(r"^(?:[-*•]\s+|\d+[.、)）]\s*)", "", line).strip()
                if point:
                    current["insights"].append(point)
        slides = [slide for slide in slides if slide["title"] and slide["insights"]]
        if not slides:
            raise APIError(502, "summary_failed", "AI 总结模型未返回有效业务分析，请重试")
        return {"agenda": [slide["title"] for slide in slides], "slides": slides}

    def _build_prompt(self, ppt_models: List[Dict[str, Any]]) -> str:
        material = []
        for q_idx, model in enumerate(ppt_models or [], start=1):
            answer_texts = []
            for answer_model in model.get("ppt_answer_models") or []:
                answer = self._truncate_text(answer_model.get("answer") or "", 2200)
                if answer:
                    answer_texts.append(answer)
            material.append(f"问题 {q_idx}：{self._truncate_text(model.get('question') or '', 180)}\n"
                            + "\n".join(answer_texts[:3]))
        return (
            "请根据以下业务问答资料，撰写适合业务汇报的中文分析提纲。\n"
            "写二到五个主题，每个主题用二级或三级 Markdown 标题；标题下面用项目符号列出业务要点。\n"
            "每个主题聚焦一个业务判断，提炼三到六条要点，包含资料支持的数字、时间、对象、排序或占比。\n"
            "最后一个主题标题为“总结”，综合概括核心发现及有依据的后续建议。\n"
            "只依据资料分析，不编造数据，不把单个时间点解释为增长趋势。\n\n"
            "业务资料：\n" + "\n\n".join(material)
        )

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        return cleaned[:limit]

    def _normalize_summary(self, summary: Dict[str, Any], ppt_models: List[Dict[str, Any]]) -> Dict[str, Any]:
        raw_slides = summary.get("slides") if isinstance(summary.get("slides"), list) else []
        slides = []
        for item in raw_slides[:5]:
            if not isinstance(item, dict):
                continue
            title = self._truncate_text(item.get("title") or "", 60)
            insights = item.get("insights") if isinstance(item.get("insights"), list) else []
            insight_limit = 8 if title == "总结" else 6
            insights = [self._truncate_text(v, 260) for v in insights if str(v or "").strip()][:insight_limit]
            if not title or not insights:
                continue
            slides.append({
                "title": title,
                "insights": insights,
                "source_questions": item.get("source_questions") if isinstance(item.get("source_questions"), list) else [],
                "visual": self._resolve_visual(item.get("visual_ref"), ppt_models),
            })

        if not slides:
            raise APIError(502, "summary_failed", "AI Summary模型未生成有效PPT结构")

        slides = slides[:5]
        if slides[-1]["title"] != "总结":
            if len(slides) >= 5:
                slides = slides[:4]
            slides.append({
                "title": "总结",
                "insights": self._build_fallback_summary(slides),
                "source_questions": [],
                "visual": None,
            })
        else:
            slides[-1]["visual"] = None

        if not any(slide.get("visual") for slide in slides):
            fallback_visual = self._first_available_visual(ppt_models)
            if fallback_visual:
                for slide in slides:
                    if slide.get("title") != "总结":
                        slide["visual"] = fallback_visual
                        break

        return {
            "agenda": [slide["title"] for slide in slides],
            "slides": slides,
        }

    @staticmethod
    def _build_fallback_summary(slides: List[Dict[str, Any]]) -> List[str]:
        result = []
        for slide in slides[:4]:
            if slide.get("insights"):
                result.append(slide["insights"][0])
        if result:
            result.extend([
                "整体来看，本次问答已经覆盖主要业务问题，可优先围绕高贡献对象、异常波动和目标达成差距展开后续追踪。",
                "建议后续结合原始明细继续拆解时间、区域、客户或产品维度，验证核心结论背后的驱动因素。",
            ])
        return result[:8] or [
            "本次对话已围绕核心业务问题完成洞察提炼，但可用于总结的结构化信息较少。",
            "建议后续结合原始问答和明细数据，继续补充关键时间、对象、指标口径和业务解释。",
        ]

    @staticmethod
    def _resolve_visual(ref: Any, ppt_models: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(ref, dict):
            return None
        try:
            q_idx = int(ref.get("question_index")) - 1
            a_idx = int(ref.get("answer_index") or 1) - 1
            c_idx = int(ref.get("chart_index")) - 1
            answer_models = ppt_models[q_idx].get("ppt_answer_models") or []
            charts = answer_models[a_idx].get("chart_data") or []
            chart_item = charts[c_idx]
            if isinstance(chart_item, dict):
                return chart_item
        except (TypeError, ValueError, IndexError, KeyError):
            return None
        return None

    @staticmethod
    def _first_available_visual(ppt_models: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for model in ppt_models or []:
            for answer_model in model.get("ppt_answer_models") or []:
                for chart_item in answer_model.get("chart_data") or []:
                    if isinstance(chart_item, dict):
                        return chart_item
        return None

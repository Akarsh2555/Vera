import os
import json
import logging
import requests
from dotenv import load_dotenv
from typing import Any

logger = logging.getLogger(__name__)

class LLMComposer:
    def __init__(self, api_key: str | None = None):
        load_dotenv()
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        # defaulting to 2.5 flash because it's way faster for this
        self.url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def compose(
        self,
        category: dict[str, Any],
        merchant: dict[str, Any],
        trigger: dict[str, Any],
        customer: dict[str, Any] | None = None,
        language_preference: str | None = None,
    ) -> dict[str, str] | None:
        if not self.is_configured():
            return None

        prompt = self._build_prompt(category, merchant, trigger, customer, language_preference)
        system_instruction = (
            "You are Vera, magicpin's merchant AI assistant. "
            "Your job is to compose highly specific, engaging, and relevant WhatsApp messages to merchants. "
            "You MUST optimize for 5 dimensions:\n"
            "1. Specificity: Use exact numbers, dates, headlines from the context. Do not use generic placeholders.\n"
            "2. Category Fit: Use the right voice (e.g., 'Dr.' for dentists, clinical vs promotional tone).\n"
            "3. Merchant Fit: Use their specific name, performance data, and language preference.\n"
            "4. Trigger Relevance: Always connect the message to the 'trigger' event (why are we messaging NOW?).\n"
            "5. Engagement Compulsion: Use curiosity, social proof, loss aversion, or effort externalization. Give a single, low-friction CTA (like 'Reply YES').\n\n"
            "CRITICAL RULES:\n"
            "- DO NOT fabricate or hallucinate any data. Only use what is provided in the context.\n"
            "- The message body should be concise and readable.\n"
            "- Return EXACTLY a JSON object with three string fields: 'body' (the message), 'cta' (the call to action shape, e.g., 'yes_stop', 'open_ended', 'none'), and 'rationale' (a short sentence explaining why this message works)."
        )

        try:
            response = requests.post(
                f"{self.url}?key={self.api_key}",
                json={
                    "system_instruction": {"parts": [{"text": system_instruction}]},
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.0,
                        "response_mime_type": "application/json"
                    }
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            text_response = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text_response:
                return None
            
            result = json.loads(text_response)
            if "body" in result and "cta" in result and "rationale" in result:
                return {
                    "body": result["body"],
                    "cta": result["cta"],
                    "rationale": result["rationale"]
                }
            return None
        except Exception as e:
            logger.error(f"LLM composition failed: {e}")
            return None

    def intent_route(self, message: str, conversation_history: list[dict[str, Any]]) -> dict[str, str | None]:
        """
        Returns a dictionary with:
        - 'intent': 'auto_reply', 'negative', 'wait', 'affirmative', 'join_intent', 'question', or 'other'
        - 'language': The detected language of the message (e.g. 'english', 'hindi', 'hinglish')
        - 'rationale': A short rationale for the classification
        """
        if not self.is_configured():
            return {"intent": None, "language": None, "rationale": None}

        history_str = json.dumps(conversation_history[-3:], indent=2) if conversation_history else "[]"
        
        system_instruction = (
            "You are an intent and language classification engine. Classify the user's latest message into one of these exact categories: "
            "'auto_reply', 'negative' (stop, unsubscribe, not interested), 'wait' (busy, later, tomorrow), "
            "'affirmative' (yes, do it, go ahead), 'join_intent' (want to join, register, onboard), "
            "'question' (what, how, why, any question), or 'other' (unclear or anything else)."
            "\n\nAlso detect the language the user is speaking in (e.g., 'english', 'hindi', 'hinglish')."
            "\n\nReturn ONLY a JSON object with fields 'intent' (string), 'language' (string), and 'rationale' (string)."
        )

        prompt = f"Recent Conversation History:\n{history_str}\n\nLatest Merchant Message: \"{message}\"\n\nClassify intent:"

        try:
            response = requests.post(
                f"{self.url}?key={self.api_key}",
                json={
                    "system_instruction": {"parts": [{"text": system_instruction}]},
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.0,
                        "response_mime_type": "application/json"
                    }
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            text_response = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text_response:
                return {"intent": None, "language": None, "rationale": None}
            
            result = json.loads(text_response)
            return {
                "intent": result.get("intent"),
                "language": result.get("language"),
                "rationale": result.get("rationale")
            }
        except Exception as e:
            logger.error(f"LLM intent routing failed: {e}")
            return {"intent": None, "language": None, "rationale": None}

    def _build_prompt(
        self,
        category: dict[str, Any],
        merchant: dict[str, Any],
        trigger: dict[str, Any],
        customer: dict[str, Any] | None,
        language_preference: str | None,
    ) -> str:
        lang_note = f"\n\n=== LANGUAGE NOTE ===\nThe merchant prefers communicating in: {language_preference}. You MUST mirror this language in your body text." if language_preference else ""
        return (
            f"=== CATEGORY CONTEXT ===\n{json.dumps(category, indent=2)}\n\n"
            f"=== MERCHANT CONTEXT ===\n{json.dumps(merchant, indent=2)}\n\n"
            f"=== TRIGGER CONTEXT ===\n{json.dumps(trigger, indent=2)}\n\n"
            f"=== CUSTOMER CONTEXT ===\n{json.dumps(customer, indent=2) if customer else 'None (message goes directly to merchant)'}"
            f"{lang_note}\n\n"
            "Compose the message based on these contexts."
        )

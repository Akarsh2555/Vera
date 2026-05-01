from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .store import ContextStore, ConversationRecord
from .llm_composer import LLMComposer


UTC = timezone.utc

NEGATIVE_SIGNALS = (
    "not interested",
    "don't send",
    "do not send",
    "stop",
    "unsubscribe",
    "no thanks",
    "nah",
    "not now",
)

WAIT_SIGNALS = ("later", "busy", "tomorrow", "next week", "after some time", "call later")
AUTO_REPLY_PATTERNS = (
    "thank you for contacting",
    "your message is important to us",
    "automated assistant",
    "automated reply",
    "our team will get back",
    "hamari team tak pahuncha",
    "jaankari ke liye bahut-bahut shukriya",
)
JOIN_INTENT_PATTERNS = ("join magicpin", "judrna", "onboard", "sign up", "register")
AFFIRMATIVE_PATTERNS = ("yes", "yeah", "go ahead", "do it", "send it", "please share", "okay", "ok")


@dataclass
class ComposedAction:
    merchant_id: str
    customer_id: str | None
    send_as: str
    trigger_id: str
    template_name: str
    template_params: list[str]
    body: str
    cta: str
    suppression_key: str
    rationale: str


class VeraEngine:
    def __init__(self, store: ContextStore) -> None:
        self.store = store
        self.llm = LLMComposer()

    def select_actions(self, now: datetime, available_triggers: list[str]) -> list[dict[str, Any]]:
        cands: list[tuple[tuple[int, float], dict[str, Any]]] = []

        for trigger_id in available_triggers:
            trigger = self.store.get_latest_payload("trigger", trigger_id)
            if not trigger:
                continue

            suppression_key = trigger.get("suppression_key", "")
            if suppression_key and self.store.was_suppression_sent(suppression_key):
                continue

            expires_at = self._parse_datetime(trigger.get("expires_at"))
            if expires_at and expires_at < now:
                continue

            merchant = self.store.get_latest_payload("merchant", trigger.get("merchant_id", ""))
            if not merchant:
                continue

            category = self.store.get_latest_payload("category", merchant.get("category_slug", ""))
            if not category:
                continue

            customer = None
            if trigger.get("scope") == "customer":
                customer = self.store.get_latest_payload("customer", trigger.get("customer_id", ""))
                if not customer:
                    continue

            last_msg_at = self.store.get_last_messaged_at(merchant["merchant_id"])
            if last_msg_at and (now - last_msg_at).total_seconds() < 6 * 3600:
                if int(trigger.get("urgency", 1)) < 4:
                    continue

            language_preference = None
            for conv in self.store.list_conversations():
                if conv["merchant_id"] == merchant["merchant_id"] and conv["detected_language"]:
                    language_preference = conv["detected_language"]
                    break

            action = self.compose(category, merchant, trigger, customer, language_preference)
            priority = (-int(trigger.get("urgency", 1)), expires_at.timestamp() if expires_at else float("inf"))
            cands.append((priority, action.__dict__))

        cands.sort(key=lambda item: item[0])
        actions: list[dict[str, Any]] = []

        for _, action in cands[:20]:
            conversation_id = self._conversation_id(action["merchant_id"], action["trigger_id"], now)
            actions.append({"conversation_id": conversation_id, **action})
            self.store.mark_suppression_sent(action["suppression_key"], now)

            trigger = self.store.get_latest_payload("trigger", action["trigger_id"]) or {}
            self.store.create_conversation(
                conversation_id=conversation_id,
                merchant_id=action["merchant_id"],
                customer_id=action["customer_id"],
                trigger_id=action["trigger_id"],
                trigger_kind=trigger.get("kind", "generic"),
                send_as=action["send_as"],
                suppression_key=action["suppression_key"],
                opened_at=now,
                body=action["body"],
                cta=action["cta"],
            )

        return actions

    def compose(
        self,
        category: dict[str, Any],
        merchant: dict[str, Any],
        trigger: dict[str, Any],
        customer: dict[str, Any] | None = None,
        language_preference: str | None = None,
    ) -> ComposedAction:
        kind = trigger.get("kind", "generic")
        merchant_name = merchant.get("identity", {}).get("name", "your business")
        owner_name = merchant.get("identity", {}).get("owner_first_name", merchant_name.split()[0])
        category_slug = merchant.get("category_slug", category.get("slug", "business"))
        top_offer = self._pick_active_offer(merchant, category)
        peer_stats = category.get("peer_stats", {})
        merchant_city = merchant.get("identity", {}).get("city", "your market")

        body = ""
        cta = "open_ended"
        rationale = ""

        if kind == "research_digest":
            # Basic RAG TF-IDF overlap retrieval
            query_str = f"{trigger.get('payload', {}).get('top_item_id', '')} {merchant_city} {category_slug}".lower()
            best_item = None
            best_score = -1
            for item in category.get("digest", []):
                item_str = f"{item.get('id', '')} {item.get('title', '')} {item.get('summary', '')} {item.get('keywords', '')}".lower()
                score = sum(1 for word in query_str.split() if word in item_str)
                if score > best_score:
                    best_score = score
                    best_item = item
            if best_item:
                trigger["payload"]["top_item_id"] = best_item.get("id")
                # Mutate category to only pass the relevant digest item to the LLM
                category["digest"] = [best_item]

        llm_result = self.llm.compose(category, merchant, trigger, customer, language_preference)
        if llm_result:
            body = llm_result["body"]
            cta = llm_result["cta"]
            rationale = llm_result["rationale"]
            return ComposedAction(
                merchant_id=merchant["merchant_id"],
                customer_id=customer.get("customer_id") if customer else None,
                send_as="merchant_on_behalf" if customer else "vera",
                trigger_id=trigger["id"],
                template_name=self._template_name(trigger, category_slug),
                template_params=self._template_params(merchant, trigger, customer, top_offer),
                body=self._clean_whitespace(body),
                cta=cta,
                suppression_key=trigger.get("suppression_key", trigger["id"]),
                rationale=rationale,
            )

        if kind == "research_digest":
            item = self._resolve_digest_item(category, trigger.get("payload", {}).get("top_item_id"))
            summary = item.get("summary", item.get("title", "new research update")).rstrip(".")
            source_text = item.get("source", "this week's digest")
            high_risk = merchant.get("customer_aggregate", {}).get("high_risk_adult_count")
            cohort_hint = (
                f"relevant to your {high_risk} high-risk adult patients"
                if high_risk
                else "relevant to the patient cohort you already see"
            )
            body = (
                f"Dr. {owner_name}, {source_text} landed. "
                f"One item looks {cohort_hint}: {summary}. "
                f"Want the 2-minute takeaway plus a patient WhatsApp draft you can reuse?"
            )
            rationale = "Research trigger turned into a cited, merchant-specific curiosity hook with a low-effort next step."
        elif kind == "regulation_change":
            item = self._resolve_digest_item(category, trigger.get("payload", {}).get("top_item_id"))
            deadline = trigger.get("payload", {}).get("deadline_iso", "the deadline")
            body = (
                f"Dr. {owner_name}, quick compliance heads-up: {item.get('title', 'a dental regulation update')} "
                f"is due by {deadline}. {item.get('actionable', 'Worth checking your current setup this week')}. "
                f"Want a 3-point chairside checklist?"
            )
            rationale = "High-urgency regulatory trigger translated into a deadline-led action message."
        elif kind == "recall_due" and customer:
            slots = trigger.get("payload", {}).get("available_slots", [])
            slot_labels = [slot.get("label") for slot in slots[:2] if slot.get("label")]
            slot_text = " or ".join(slot_labels) if slot_labels else "this week"
            service_due = trigger.get("payload", {}).get("service_due", "follow-up visit").replace("_", " ")
            name = customer.get("identity", {}).get("name", "there")
            last_visit = customer.get("relationship", {}).get("last_visit", "")
            body = (
                f"Hi {name}, Dr. {owner_name}'s clinic here. It's been a while since your last visit on {last_visit} "
                f"and your {service_due} window is opening. Apke liye {slot_text} hold kar sakte hain. "
                f"{top_offer.get('title', 'your follow-up visit')}. Reply YES and I'll hold the best slot."
            )
            cta = "yes_stop"
            rationale = "Recall reminder uses visit timing, real slots, and a concrete offer with a single binary CTA."
        elif kind == "perf_dip":
            metric = trigger.get("payload", {}).get("metric", "performance")
            delta_pct = abs(int(round(trigger.get("payload", {}).get("delta_pct", 0) * 100)))
            baseline = trigger.get("payload", {}).get("vs_baseline")
            peer_ctr = peer_stats.get("avg_ctr")
            baseline_text = f" versus a baseline of {baseline}" if baseline else ""
            peer_text = f" Peer CTR in {merchant_city} is around {peer_ctr:.1%}." if peer_ctr else ""
            body = (
                f"{owner_name}, your {metric} slipped {delta_pct}% this week{baseline_text}. "
                f"One fix I'd push first: revive {top_offer.get('title', 'your strongest service offer')} and pair it with a fresh GBP post."
                f"{peer_text} Want me to draft the post copy?"
            )
            rationale = "Performance dip message uses merchant-specific numbers and converts them into one concrete recovery action."
        elif kind == "renewal_due":
            days = trigger.get("payload", {}).get("days_remaining", merchant.get("subscription", {}).get("days_remaining", ""))
            amount = trigger.get("payload", {}).get("renewal_amount")
            amount_text = f" Renewal is Rs {amount}." if amount else ""
            body = (
                f"{owner_name}, your {merchant.get('subscription', {}).get('plan', 'plan')} renewal is due in {days} days. "
                f"Before you decide, I can package the last 30-day wins plus 2 quick moves to recover more calls from Google."
                f"{amount_text} Want the short ROI view?"
            )
            rationale = "Renewal reminder is framed as value justification instead of a generic bill nudge."
        elif kind == "festival_upcoming":
            festival = trigger.get("payload", {}).get("festival", "the upcoming festival")
            days_until = trigger.get("payload", {}).get("days_until", "")
            body = (
                f"{owner_name}, {festival} is {days_until} days out. "
                f"For {merchant_name}, I'd avoid flat discounts and push one sharp hook instead: "
                f"{top_offer.get('title', 'your hero service')} as the lead-in offer. Want a GBP post + WhatsApp caption set?"
            )
            rationale = "Festival trigger converted into a category-correct service-plus-price angle."
        elif kind == "wedding_package_followup" and customer:
            name = customer.get("identity", {}).get("name", "there")
            days_to_wedding = trigger.get("payload", {}).get("days_to_wedding", "")
            preferred = customer.get("preferences", {}).get("preferred_slots", "Saturday")
            body = (
                f"Hi {name}, {owner_name} from {merchant_name} here. {days_to_wedding} days to the wedding is a strong window to start skin-prep seriously. "
                f"I'd start with a 30-day bridal prep block and hold your usual {preferred} slot if that helps. Want me to reserve the first session?"
            )
            cta = "yes_stop"
            rationale = "Bridal follow-up stays relationship-led and uses the wedding countdown as the urgency anchor."
        elif kind == "curious_ask_due":
            body = (
                f"Hi {owner_name}, quick check: what service is being asked for most this week at {merchant_name}? "
                f"I'll turn your answer into one Google post and one fast WhatsApp reply you can reuse. Takes 2 minutes."
            )
            rationale = "Curious ask uses the asking-the-merchant lever and offers immediate reciprocity."
        elif kind == "winback_eligible":
            since = trigger.get("payload", {}).get("days_since_expiry", "")
            lapsed = trigger.get("payload", {}).get("lapsed_customers_added_since_expiry", "")
            body = (
                f"{owner_name}, it's been {since} days since the plan expired and you've likely lost momentum with {lapsed} customers drifting out. "
                f"I can build a lean winback pack around {top_offer.get('title', 'one simple comeback offer')} instead of restarting from scratch. Want the first draft?"
            )
            rationale = "Winback note focuses on recovery momentum and removes restart friction."
        elif kind == "ipl_match_today":
            payload = trigger.get("payload", {})
            match_name = payload.get("match", "today's match")
            body = (
                f"Quick heads-up {owner_name}: {match_name} is on tonight at {payload.get('venue', 'the local stadium')}. "
                f"For {merchant_name}, I'd skip a dine-in push and turn {top_offer.get('title', 'your current promo')} into a delivery-first match-night special. "
                f"Want the Swiggy banner line + Insta story copy?"
            )
            rationale = "Event trigger is interpreted into an operator recommendation, not just repeated back."
        elif kind == "review_theme_emerged":
            theme = trigger.get("payload", {}).get("theme", "reviews").replace("_", " ")
            quote = trigger.get("payload", {}).get("common_quote", "customers noticed this")
            count = trigger.get("payload", {}).get("occurrences_30d", "")
            body = (
                f"{owner_name}, {count} recent reviews are clustering around {theme}. "
                f"One customer literally said: \"{quote}\". Want me to draft a reply pattern plus one operational fix you can publish on Google this week?"
            )
            rationale = "Review alert anchors on an actual customer quote to make the issue feel real and actionable."
        elif kind == "milestone_reached":
            value_now = trigger.get("payload", {}).get("value_now", "")
            milestone = trigger.get("payload", {}).get("milestone_value", "")
            body = (
                f"{owner_name}, you're at {value_now} reviews and close to the {milestone} mark. "
                f"This is a good moment to line up one thank-you plus ask-for-review nudge while the momentum is live. Want me to draft it?"
            )
            rationale = "Milestone trigger turns momentum into the next measurable action."
        elif kind == "active_planning_intent":
            body = self._planning_response(merchant, trigger, top_offer)
            rationale = "Active planning intents are routed straight into draft mode instead of more qualification."
        elif kind == "seasonal_perf_dip":
            delta_pct = abs(int(round(trigger.get("payload", {}).get("delta_pct", 0) * 100)))
            season_note = trigger.get("payload", {}).get("season_note", "seasonal window").replace("_", " ")
            members = merchant.get("customer_aggregate", {}).get("total_active_members")
            members_text = f" You already have {members} active members to protect." if members else ""
            body = (
                f"{owner_name}, your views are down {delta_pct}% this week, but this looks like the normal {season_note} dip, not a broken funnel."
                f"{members_text} I'd shift effort to retention for the next few weeks. Want a summer challenge draft?"
            )
            rationale = "Seasonal dip message reduces panic and reframes the trigger into a better decision."
        elif kind == "customer_lapsed_hard" and customer:
            name = customer.get("identity", {}).get("name", "there")
            days = trigger.get("payload", {}).get("days_since_last_visit", "")
            focus = trigger.get("payload", {}).get("previous_focus", "your earlier goal").replace("_", " ")
            body = (
                f"Hi {name}, {owner_name} from {merchant_name} here. It's been about {days} days since your last visit, which happens to a lot of members. "
                f"We've got a restart option that fits your {focus} goal. Want me to hold one no-pressure trial session for you this week?"
            )
            cta = "yes_stop"
            rationale = "Winback copy stays warm, low-pressure, and specific to the customer's past goal."
        elif kind == "trial_followup" and customer:
            name = customer.get("identity", {}).get("name", "there")
            options = trigger.get("payload", {}).get("next_session_options", [])
            slot = options[0].get("label") if options else "this weekend"
            body = (
                f"Hi {name}, thanks for trying the session at {merchant_name}. "
                f"The next strong slot is {slot}, and it's the easiest one for building continuity early. Want me to hold it for you?"
            )
            cta = "yes_stop"
            rationale = "Trial follow-up converts a fresh experience into a low-friction next booking."
        elif kind == "supply_alert":
            payload = trigger.get("payload", {})
            batches = ", ".join(payload.get("affected_batches", []))
            body = (
                f"{owner_name}, urgent stock alert: {payload.get('molecule', 'one SKU')} batches {batches} from {payload.get('manufacturer', 'the manufacturer')} are under recall. "
                f"Please pull those units from shelves first. Want a short customer-safe response template for walk-ins?"
            )
            rationale = "Supply alert prioritizes safety, specificity, and immediate operator action."
        elif kind == "chronic_refill_due" and customer:
            name = customer.get("identity", {}).get("name", "there")
            meds = ", ".join(trigger.get("payload", {}).get("molecule_list", [])[:3])
            stock_out = trigger.get("payload", {}).get("stock_runs_out_iso", "")
            body = (
                f"Namaste {name}, {merchant_name} se reminder: your refill for {meds} may run out by {stock_out[:10]}. "
                f"Agar chahein to hum delivery ready kar dein. Reply YES and we'll line it up."
            )
            cta = "yes_stop"
            rationale = "Refill reminder uses medication specifics and a simple fulfillment-oriented CTA."
        elif kind == "category_seasonal":
            trends = ", ".join(trigger.get("payload", {}).get("trends", [])[:3]).replace("_", " ")
            body = (
                f"{owner_name}, summer demand is shifting fast: {trends}. "
                f"For {merchant_name}, I'd refresh shelves and your Google description together so walk-ins and search demand point the same way. Want the short action list?"
            )
            rationale = "Seasonal category trigger turns market data into merchandising plus listing action."
        elif kind == "gbp_unverified":
            uplift = int(round(trigger.get("payload", {}).get("estimated_uplift_pct", 0) * 100))
            path = trigger.get("payload", {}).get("verification_path", "the usual path").replace("_", " ")
            body = (
                f"{owner_name}, your Google Business Profile is still unverified. That alone can cap discovery hard. "
                f"Expected upside after verification is roughly {uplift}% on visibility for merchants like you. Verification path: {path}. Want the fastest step-by-step?"
            )
            rationale = "Verification nudge uses a concrete upside and removes ambiguity around the next step."
        elif kind == "cde_opportunity":
            item = self._resolve_digest_item(category, trigger.get("payload", {}).get("digest_item_id"))
            body = (
                f"Dr. {owner_name}, small CDE opportunity: {item.get('title', 'a useful session')} is live soon. "
                f"{item.get('actionable', '')} If you want, I can also draft one patient-facing takeaway from it for your clinic WhatsApp."
            )
            rationale = "CDE trigger creates professional value first, then extends it into merchant growth."
        elif kind == "competitor_opened":
            payload = trigger.get("payload", {})
            body = (
                f"Dr. {owner_name}, a new clinic called {payload.get('competitor_name', 'a nearby competitor')} opened {payload.get('distance_km', '?')} km away "
                f"with {payload.get('their_offer', 'an aggressive offer')}. I would not race them on price blindly. "
                f"Want a sharper response angle for {merchant_name} based on trust + treatment fit?"
            )
            rationale = "Competitor alert avoids panic-discounting and opens a more strategic next step."
        elif kind == "perf_spike":
            likely_driver = trigger.get("payload", {}).get("likely_driver", "your recent activity").replace("_", " ")
            delta_pct = int(round(trigger.get("payload", {}).get("delta_pct", 0) * 100))
            body = (
                f"{owner_name}, nice one: calls are up {delta_pct}% this week, likely from {likely_driver}. "
                f"This is a good time to double down while intent is warm. Want me to spin the winning angle into one more Google post?"
            )
            rationale = "Positive performance spike becomes momentum amplification rather than a passive congrats."
        elif kind == "dormant_with_vera":
            days = trigger.get("payload", {}).get("days_since_last_merchant_message", "")
            last_topic = trigger.get("payload", {}).get("last_topic", "the last discussion").replace("_", " ")
            body = (
                f"{owner_name}, we have not spoken in {days} days since the {last_topic} thread. "
                f"I do not want to send you generic nudges, so here is the most useful next thing I can do: package one quick win around {top_offer.get('title', 'your strongest lever')}. Want it?"
            )
            rationale = "Dormancy message acknowledges the gap and re-enters with a value-first hook."
        else:
            body = (
                f"{owner_name}, I spotted a live opportunity for {merchant_name}. "
                f"The most practical next move is to use {top_offer.get('title', 'your strongest current offer')} with a single, specific CTA. Want me to draft it?"
            )
            rationale = "Fallback message stays specific and action-oriented even for unseen trigger kinds."

        return ComposedAction(
            merchant_id=merchant["merchant_id"],
            customer_id=customer.get("customer_id") if customer else None,
            send_as="merchant_on_behalf" if customer else "vera",
            trigger_id=trigger["id"],
            template_name=self._template_name(trigger, category_slug),
            template_params=self._template_params(merchant, trigger, customer, top_offer),
            body=self._clean_whitespace(body),
            cta=cta,
            suppression_key=trigger.get("suppression_key", trigger["id"]),
            rationale=rationale,
        )

    def handle_reply(self, conversation: ConversationRecord, message: str, received_at: datetime) -> dict[str, Any]:
        normalized = self._normalize(message)
        
        intent_data = self.llm.intent_route(message, conversation.history)
        intent = intent_data.get("intent")
        detected_language = intent_data.get("language")
        rationale = intent_data.get("rationale") or ""
        
        if intent == "auto_reply":
            auto_reply_detected = True
        elif intent:
            auto_reply_detected = False
        else:
            auto_reply_detected = self._looks_like_auto_reply(conversation, normalized)

        merchant = self.store.get_latest_payload("merchant", conversation.merchant_id) or {}
        category = self.store.get_latest_payload("category", merchant.get("category_slug", "")) or {}
        trigger = self.store.get_latest_payload("trigger", conversation.trigger_id) or {}
        customer = self.store.get_latest_payload("customer", conversation.customer_id) if conversation.customer_id else None

        self.store.update_conversation(
            conversation.conversation_id,
            turn_count=conversation.turn_count + 1,
            detected_language=detected_language,
            append_event={"at": received_at.isoformat(), "from": "user", "body": message, "intent": intent, "rationale": rationale},
            updated_at=received_at,
        )

        if intent == "negative" or (not intent and any(signal in normalized for signal in NEGATIVE_SIGNALS)):
            self.store.update_conversation(conversation.conversation_id, status="ended", updated_at=received_at)
            return {
                "action": "end",
                "rationale": "Merchant/customer opted out or signaled disinterest, so the conversation should end cleanly.",
            }

        if intent == "wait" or (not intent and any(signal in normalized for signal in WAIT_SIGNALS)):
            self.store.update_conversation(conversation.conversation_id, status="waiting", updated_at=received_at)
            return {
                "action": "wait",
                "wait_seconds": 1800,
                "rationale": "The reply asks for more time, so the bot should back off for 30 minutes.",
            }

        if auto_reply_detected:
            auto_hits = conversation.auto_reply_hits + 1
            self.store.update_conversation(
                conversation.conversation_id,
                auto_reply_hits=auto_hits,
                updated_at=received_at,
            )
            if auto_hits >= 2:
                self.store.update_conversation(conversation.conversation_id, status="ended", updated_at=received_at)
                return {
                    "action": "end",
                    "rationale": "Repeated auto-reply detected; continuing would waste turns and hurt replay quality.",
                }
            body = "Samajh gaya. Before I drop this, should I send the useful part directly for the owner to review at one go?"
            self._append_bot_turn(conversation.conversation_id, body, "yes_stop", received_at)
            return {
                "action": "send",
                "body": body,
                "cta": "yes_stop",
                "rationale": "First auto-reply detected; one graceful owner-check is worth trying before exiting.",
            }

        if intent == "join_intent" or (not intent and any(signal in normalized for signal in JOIN_INTENT_PATTERNS)):
            body = (
                f"Perfect. I will switch straight to onboarding mode for {merchant.get('identity', {}).get('name', 'your business')}. "
                f"Reply with the best owner phone number and city, or send CALL if you want a quick callback setup."
            )
            self._append_bot_turn(conversation.conversation_id, body, "open_ended", received_at)
            return {
                "action": "send",
                "body": body,
                "cta": "open_ended",
                "rationale": "Explicit join intent should move immediately into action capture, not more persuasion.",
            }

        if intent == "affirmative" or (not intent and self._is_affirmative(normalized)):
            body = self._affirmative_follow_up(trigger, merchant, category, customer)
            self._append_bot_turn(conversation.conversation_id, body, "open_ended", received_at)
            return {
                "action": "send",
                "body": body,
                "cta": "open_ended",
                "rationale": "Positive engagement should be rewarded with the next-best artifact or concrete step.",
            }

        if intent == "question" or (not intent and ("?" in message or normalized.startswith(("what", "how", "why", "which")))):
            body = self._question_follow_up(trigger, merchant, customer)
            self._append_bot_turn(conversation.conversation_id, body, "open_ended", received_at)
            return {
                "action": "send",
                "body": body,
                "cta": "open_ended",
                "rationale": "The bot should answer the question directly and keep the conversation moving with one focused next step.",
            }

        body = "Understood. I can keep this simple and send one ready-to-use draft for review. Want the short version or the detailed one?"
        self._append_bot_turn(conversation.conversation_id, body, "open_ended", received_at)
        return {
            "action": "send",
            "body": body,
            "cta": "open_ended",
            "rationale": "Fallback keeps momentum without overcomplicating the next turn.",
        }

    def _affirmative_follow_up(
        self,
        trigger: dict[str, Any],
        merchant: dict[str, Any],
        category: dict[str, Any],
        customer: dict[str, Any] | None,
    ) -> str:
        kind = trigger.get("kind", "generic")
        if kind == "research_digest":
            item = self._resolve_digest_item(category, trigger.get("payload", {}).get("top_item_id"))
            takeaway = item.get("actionable", item.get("summary", "worth applying this week"))
            return self._clean_whitespace(
                f"Sharing the short takeaway now: {item.get('title', 'the top item')} - {takeaway}. "
                f"If you want, I will also draft a patient-facing WhatsApp in your clinic's tone."
            )
        if kind == "active_planning_intent":
            return "Here is the next move I'd ship first: tighten the draft into a customer-facing version plus a GBP post so you can test the idea immediately."
        if kind in {"recall_due", "customer_lapsed_hard", "trial_followup", "chronic_refill_due", "wedding_package_followup"} and customer:
            customer_name = customer.get("identity", {}).get("name", "the customer")
            return (
                f"Done. I will treat that as a hold request and keep the next best slot ready. "
                f"If timing changes, just send the preferred day and I will adapt the draft for {customer_name}."
            )
        if kind == "regulation_change":
            deadline = trigger.get("payload", {}).get("deadline_iso", "")
            return (
                f"Great. The clean checklist is: 1) verify current setup, 2) log what needs updating, 3) close the SOP update before {deadline}. "
                f"If you want, I will turn that into a staff-ready note."
            )
        return (
            f"Nice. I will turn that into one ready-to-use asset for "
            f"{merchant.get('identity', {}).get('name', 'your business')} so you can review instead of starting from scratch."
        )

    def _question_follow_up(
        self,
        trigger: dict[str, Any],
        merchant: dict[str, Any],
        customer: dict[str, Any] | None,
    ) -> str:
        kind = trigger.get("kind", "generic")
        if kind == "active_planning_intent":
            return "I'd start with the smallest testable version first so you can validate demand quickly, then expand pricing or packaging after the first week."
        if kind == "renewal_due":
            return "The point is to show whether the next cycle can pay for itself. I'd compare your current call flow, active offers, and the quickest listing fix before deciding."
        if kind in {"recall_due", "trial_followup", "customer_lapsed_hard"} and customer:
            return "I'm optimizing around convenience first, because that usually matters more than copy. If you share the preferred day or slot, I can tailor the reminder properly."
        return "The short answer: I'm anchoring this on your live merchant context so the message feels specific, useful, and easy to act on."

    def _planning_response(self, merchant: dict[str, Any], trigger: dict[str, Any], top_offer: dict[str, Any]) -> str:
        topic = trigger.get("payload", {}).get("intent_topic", "")
        owner_name = merchant.get("identity", {}).get("owner_first_name", "there")
        locality = merchant.get("identity", {}).get("locality", "your area")
        merchant_name = merchant.get("identity", {}).get("name", "Your business")

        if "corporate_bulk_thali" in topic:
            return self._clean_whitespace(
                f"{owner_name}, here's a starter version you can test next week:\n"
                f"{merchant_name} Corporate Thali for {locality}\n"
                f"- 10 thalis @ Rs 125 each + free delivery\n"
                f"- 25 thalis @ Rs 115 each + 2 free filter coffees\n"
                f"- 50+ thalis @ Rs 105 each + 1 free dosa platter\n"
                f"- Orders locked a day before by 5pm\n"
                f"Want me to turn this into a 3-line WhatsApp pitch for office admins?"
            )
        if "kids_yoga" in topic:
            return self._clean_whitespace(
                f"{owner_name}, I'd keep the first version tight: 4-week kids yoga camp, 3 classes/week, age 7-12, weekend-led, and a parent update after every week. "
                f"A clean starting price is Rs 2,499 with one trial class included. Want the GBP post + parent WhatsApp draft?"
            )
        return self._clean_whitespace(
            f"{owner_name}, instead of another round of questions, I'd ship a first draft now around {top_offer.get('title', 'your strongest offer')} and let you react to something concrete. Want that version?"
        )

    def _resolve_digest_item(self, category: dict[str, Any], item_id: str | None) -> dict[str, Any]:
        for item in category.get("digest", []):
            if item.get("id") == item_id:
                return item
        return category.get("digest", [{}])[0] if category.get("digest") else {}

    def _pick_active_offer(self, merchant: dict[str, Any], category: dict[str, Any]) -> dict[str, Any]:
        for offer in merchant.get("offers", []):
            if offer.get("status") == "active":
                return offer
        return category.get("offer_catalog", [{}])[0] if category.get("offer_catalog") else {"title": "a focused offer"}

    def _template_name(self, trigger: dict[str, Any], category_slug: str) -> str:
        prefix = "merchant" if trigger.get("scope") == "merchant" else "customer"
        return f"vera_{prefix}_{category_slug}_{trigger.get('kind', 'generic')}_v1"

    def _template_params(
        self,
        merchant: dict[str, Any],
        trigger: dict[str, Any],
        customer: dict[str, Any] | None,
        offer: dict[str, Any],
    ) -> list[str]:
        params = [merchant.get("identity", {}).get("owner_first_name", "there")]
        if customer:
            params.append(customer.get("identity", {}).get("name", "there"))
        params.append(trigger.get("kind", "trigger").replace("_", " "))
        params.append(offer.get("title", "offer"))
        return [str(param) for param in params if param]

    def _looks_like_auto_reply(self, conversation: ConversationRecord, normalized: str) -> bool:
        if any(pattern in normalized for pattern in AUTO_REPLY_PATTERNS):
            return True

        prior_user_messages = [
            self._normalize(item["body"])
            for item in conversation.history
            if item.get("from") == "user" and item.get("body")
        ]
        if prior_user_messages and prior_user_messages[-1] == normalized:
            return True
        return False

    def _is_affirmative(self, normalized: str) -> bool:
        if normalized in {"y", "yes", "ok", "okay"}:
            return True
        return any(pattern in normalized for pattern in AFFIRMATIVE_PATTERNS)

    def _append_bot_turn(self, conversation_id: str, body: str, cta: str, at: datetime) -> None:
        self.store.update_conversation(
            conversation_id,
            last_bot_message=body,
            last_cta=cta,
            append_event={"at": at.isoformat(), "from": "bot", "body": body, "cta": cta},
            updated_at=at,
        )

    def _conversation_id(self, merchant_id: str, trigger_id: str, now: datetime) -> str:
        short_trigger = trigger_id.replace("trg_", "").replace(":", "_")
        return f"conv_{merchant_id}_{short_trigger}_{now.strftime('%H%M%S')}"

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().strip().split())

    def _clean_whitespace(self, text: str) -> str:
        lines = [line.strip() for line in text.strip().splitlines()]
        return "\n".join(lines)

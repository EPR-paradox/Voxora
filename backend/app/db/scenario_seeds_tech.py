"""Formal technical meetings: overlay algorithms, software, fab customers, other departments.

Different from the other two meeting sets in one way that matters: the substance here is the work
itself. `design-review-scope-01` is about a plan and a date; these are about residuals, matching,
sampling plans and defect recipes — the vocabulary a metrology engineer is actually paid to argue
in, with the numbers and the uncertainty that come with it (which is exactly what makes them hard in
a second language: you have to disagree about data, hedge correctly, and commit to a next step in
front of a customer).

Design notes:

- **Recurring colleagues keep their keys.** `algo_lead` and `sw_eng` appear in several of these, and
  voices
  are derived from the cast key (§9.1), so the same person sounds the same in every meeting. A team
  you recognise across sessions is worth more than five sets of strangers.
- **The meeting runs on an agenda, not on the learner.** Each scenario writes its agenda into
  `roleplay_instructions` and tells the participants to drive it, raise their own numbers and assign
  actions. That is what makes these usable for a learner who only listens: the room does not stall
  waiting for a turn that is not coming.
- **Nobody corrects the learner's English, and nobody judges the technical conclusion** (§8.4): the
  participants may disagree with each other and with the learner about the *work*, which is the
  point — being contradicted about a model order is not the same as being told your grammar is
  wrong.
- **No real company, fab or customer is named** (§1.4). `industry_segment` stays `equipment` because
  the
  client turns that field into a filter chip — inventing a new value for five scenarios adds a
  filter for no one's benefit.
"""

from __future__ import annotations

from typing import Any


def _rubric() -> dict[str, Any]:
    """A fresh copy per scenario: seeds never share one object (see test_scenario_seeds)."""
    return {
        "version": "english-communication-v1",
        "dimensions": [
            "clarity",
            "response_relevance",
            "professional_tone",
            "naturalness",
        ],
    }


# : The learner's own role in these meetings: metrology algorithms on the equipment side.
TECH_ROLES = ["algorithm_engineer", "metrology_software_engineer"]

TECH_MEETING_SEEDS: list[dict[str, Any]] = [
    {
        "slug": "overlay-residual-review-01",
        "title": "Review an overlay residual excursion",
        "summary": "Separate a model problem from a process problem first.",
        "category": "workplace",
        "industry_segment": "equipment",
        "companies": [],
        "roles": TECH_ROLES,
        "difficulty": 3,
        "english_level": "B2",
        "situation": (
            "Last week's lot came off the litho track with overlay residuals about 40% above the "
            "previous baseline. The algorithms group and the software group meet to decide whether "
            "this is a model problem — order too low, a correctable missing — or a process and "
            "measurement problem."
        ),
        "cast": [
            {
                "key": "algo_lead",
                "name": "Dr. Nadia Farrow",
                "title": "Algorithms Lead",
                "personality": "wants the residual decomposed before anyone changes the model",
                "communication_style": "asks for the term that explains the most variance",
            },
            {
                "key": "sw_eng",
                "name": "Tobias Lang",
                "title": "Software Engineer",
                "personality": "owns the data pipeline, and says when one of its fields is missing",
                "communication_style": "answers with what the data path does, in order",
            },
            {
                "key": "apps_eng",
                "name": "Grace Okonjo",
                "title": "Applications Engineer",
                "personality": "sits between the fab and the code, reports what the customer saw",
                "communication_style": "starts from the customer's words, then translates",
            },
        ],
        "user_objective": (
            "Take part in the diagnosis: say what you think is driving the residual, ask for the "
            "data that would settle it, and agree one thing to check and by when."
        ),
        "target_skills": ["technical_diagnosis", "hedging_uncertainty", "agreeing_next_steps"],
        "target_expressions": [
            {
                "expression": "Let's separate the two contributions.",
                "meaning": "Split a mixed effect before arguing about either half.",
                "usage": "Let's separate the two — how much is process and how much is model?",
            },
            {
                "expression": "That's within measurement noise, isn't it?",
                "meaning": "Question a number's significance without dismissing it.",
                "usage": "A two-nanometre shift is within measurement noise, isn't it?",
            },
        ],
        "roleplay_instructions": (
            "Run an eight-minute technical review. Agenda: (1) what the customer reported, (2) "
            "decompose the residual into model, process and measurement contributions, (3) agree "
            "what to check next and by when. The participants run the meeting and may disagree "
            "with each other and with the learner about the technical reading — argue from "
            "numbers, ask for evidence, and use uncertainty language the way engineers do. Never "
            "correct the learner's English and never judge whether their technical conclusion is "
            "right. Wrap up when the agenda is done."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 8,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "scanner-matching-workshop-01",
        "title": "Decide how to handle scanner-to-scanner mismatch",
        "summary": "Weigh a baseline correction against compensating in the model.",
        "category": "workplace",
        "industry_segment": "equipment",
        "companies": [],
        "roles": TECH_ROLES,
        "difficulty": 3,
        "english_level": "B2",
        "situation": (
            "Two scanners in the same line, and the matching error at the edge of the field is "
            "eating most of the overlay budget on the critical layer. The options on the table: "
            "run a baseline correction, which costs hours of tool time, or compensate for it in "
            "the model."
        ),
        "cast": [
            {
                "key": "algo_lead",
                "name": "Dr. Nadia Farrow",
                "title": "Algorithms Lead",
                "personality": "wants the trade-off quantified, not described",
                "communication_style": "asks what a choice costs as well as what it fixes",
            },
            {
                "key": "sw_eng",
                "name": "Tobias Lang",
                "title": "Software Engineer",
                "personality": "cares about what the change does to the next release",
                "communication_style": "asks who has to maintain the workaround",
            },
            {
                "key": "integr",
                "name": "Hyun-Woo Park",
                "title": "Integration Engineer",
                "personality": "has the tool schedule and knows what the delay costs",
                "communication_style": "gives dates, refuses vague ones",
            },
        ],
        "user_objective": (
            "Argue for one of the two options with a reason, ask what each costs in tool time and "
            "quality margin, and get the meeting to a decision."
        ),
        "target_skills": [
            "quantifying_a_tradeoff",
            "justifying_technical_choice",
            "reaching_a_decision",
        ],
        "target_expressions": [
            {
                "expression": "Can we quantify the trade-off?",
                "meaning": "Move a discussion from opinions to numbers.",
                "usage": "Can we quantify the trade-off in tool hours against residual?",
            },
            {
                "expression": "That's a workaround we'd own forever.",
                "meaning": "Name the long-term cost of a short-term fix.",
                "usage": "Compensating in the model is a workaround we'd own forever.",
            },
        ],
        "roleplay_instructions": (
            "Run a seven-minute workshop. Agenda: (1) how large the mismatch is and where it "
            "shows, (2) what a baseline correction costs against what compensation costs, (3) "
            "decide and name the owner. The participants push for quantification, may disagree "
            "with each other, and should not wait for the learner to move the agenda along. Never "
            "correct the learner's English and never judge their technical conclusion."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 7,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "fab-customer-tech-call-01",
        "title": "Handle a fab customer's overlay escalation",
        "summary": "Report what the data supports, and commit only to what you can keep.",
        "category": "workplace",
        "industry_segment": "equipment",
        "companies": [],
        "roles": TECH_ROLES,
        "difficulty": 3,
        "english_level": "B2",
        "situation": (
            "A customer process engineer says the critical layer has been out of spec on three "
            "lots and wants a root cause within 48 hours. You are on the vendor side with partial "
            "data, and an account manager who would like to promise more than the data supports."
        ),
        "cast": [
            {
                "key": "customer_pe",
                "name": "Rita Halvorsen",
                "title": "Customer Process Engineer",
                "personality": "under pressure from her own management and short on patience",
                "communication_style": "asks closed questions, repeats the ones left unanswered",
            },
            {
                "key": "algo_lead",
                "name": "Dr. Nadia Farrow",
                "title": "Algorithms Lead",
                "personality": "will not state more than the data shows",
                "communication_style": "separates what is known from what is assumed",
            },
            {
                "key": "account",
                "name": "Peter Nkemelu",
                "title": "Account Manager",
                "personality": "wants the customer to leave happy today",
                "communication_style": "offers dates and comfort before the engineers have agreed",
            },
        ],
        "user_objective": (
            "Report what the data supports, resist committing to a root cause you do not have, and "
            "offer a specific interim step the customer can act on."
        ),
        "target_skills": ["managing_a_customer", "committing_carefully", "technical_explanation"],
        "target_expressions": [
            {
                "expression": "What we can commit to by Thursday is...",
                "meaning": "Offer a promise you can actually keep.",
                "usage": "What we can commit to by Thursday is a decomposition of the residual.",
            },
            {
                "expression": "I don't want to guess in front of the customer.",
                "meaning": "Refuse to speculate without sounding obstructive.",
                "usage": "I'd rather wait for the data than guess in front of the customer.",
            },
        ],
        "roleplay_instructions": (
            "Run an eight-minute customer call. Agenda: (1) what the customer observed on the "
            "three lots, (2) what the vendor data does and does not support, (3) an interim step "
            "and a date. The customer presses for a root cause and the account manager pushes for "
            "a friendlier promise, so the learner has to hold a line without losing the room. "
            "Never correct the learner's English and never judge their technical conclusion."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 8,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "sampling-plan-tradeoff-01",
        "title": "Agree a sampling plan under throughput pressure",
        "summary": "Buy control without paying for it in tool time.",
        "category": "workplace",
        "industry_segment": "equipment",
        "companies": [],
        "roles": TECH_ROLES,
        "difficulty": 3,
        "english_level": "B2",
        "situation": (
            "The fab wants tighter control on the critical layer, which means more measurement "
            "points per wafer, which means more tool time the line does not have. The algorithms "
            "group, the control engineer and the software group have to agree on a sampling plan."
        ),
        "cast": [
            {
                "key": "algo_lead",
                "name": "Dr. Nadia Farrow",
                "title": "Algorithms Lead",
                "personality": "thinks in terms of which points carry the signal",
                "communication_style": "proposes a layout and says what it can and cannot see",
            },
            {
                "key": "apc_eng",
                "name": "Sofia Marchetti",
                "title": "Advanced Process Control Engineer",
                "personality": "owns the control loop and its stability",
                "communication_style": "talks in terms of what the loop can correct and how fast",
            },
            {
                "key": "sw_eng",
                "name": "Tobias Lang",
                "title": "Software Engineer",
                "personality": "cares whether the plan survives contact with the release schedule",
                "communication_style": "asks what has to change in the pipeline",
            },
        ],
        "user_objective": (
            "Propose or challenge a sampling plan on its merits: what it buys in control, what it "
            "costs in tool time, and what it breaks downstream."
        ),
        "target_skills": [
            "technical_negotiation",
            "cost_benefit_language",
            "clarifying_requirements",
        ],
        "target_expressions": [
            {
                "expression": "What does that give us in control terms?",
                "meaning": "Force a proposal to state its benefit concretely.",
                "usage": "What does that give us in control terms — how much less rework?",
            },
            {
                "expression": "Where do you want the extra points?",
                "meaning": "Turn an abstract request into a decision.",
                "usage": "Where do you want the extra points — field edge or wafer edge?",
            },
        ],
        "roleplay_instructions": (
            "Run a seven-minute planning meeting. Agenda: (1) what the current plan fails to "
            "catch, (2) two candidate layouts and what each buys, (3) pick one and note what it "
            "costs. The control engineer argues from loop stability, the algorithms lead from "
            "signal — they may talk past each other. Never correct the learner's English and never "
            "judge their technical conclusion."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 7,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "defect-review-cross-dept-01",
        "title": "Cross-department review of a missed defect class",
        "summary": "Trade sensitivity against false alarms, with two departments pulling apart.",
        "category": "workplace",
        "industry_segment": "equipment",
        "companies": [],
        "roles": TECH_ROLES,
        "difficulty": 3,
        "english_level": "B2",
        "situation": (
            "A defect class slipped past the inspection recipe and reached the next step. The "
            "process team wants the sensitivity raised; the software team warns that the same "
            "change floods the review station with false alarms, and the review capacity is "
            "already tight."
        ),
        "cast": [
            {
                "key": "process_eng",
                "name": "Marcus Feld",
                "title": "Process Engineer",
                "personality": "is the one who has to explain the escape upwards",
                "communication_style": "states the risk in terms of what reaches the customer",
            },
            {
                "key": "sw_eng",
                "name": "Tobias Lang",
                "title": "Software Engineer",
                "personality": "defends the review station's capacity with numbers",
                "communication_style": "puts two options side by side, asks which hurts less",
            },
            {
                "key": "algo_lead",
                "name": "Dr. Nadia Farrow",
                "title": "Algorithms Lead",
                "personality": "wants the threshold question answered with data, not with feelings",
                "communication_style": "asks for the capture rate at each candidate threshold",
            },
        ],
        "user_objective": (
            "Contribute to the trade-off: name what a higher sensitivity costs, ask for the "
            "numbers that decide it, and help the room land on a threshold and a way to check it."
        ),
        "target_skills": ["cross_team_communication", "weighing_risks", "agreeing_actions"],
        "target_expressions": [
            {
                "expression": "Raising the sensitivity will cost us on the nuisance side.",
                "meaning": "State the other half of a trade-off without blocking the first half.",
                "usage": "Raising the sensitivity will cost us roughly double the nuisance rate.",
            },
            {
                "expression": "Can we pilot it on one layer first?",
                "meaning": "Reduce the risk of a decision instead of arguing about it.",
                "usage": "Can we pilot it on one layer for a week before rolling it out?",
            },
        ],
        "roleplay_instructions": (
            "Run a seven-minute cross-department review. Agenda: (1) what escaped and how, (2) "
            "what a higher sensitivity costs in nuisance rate and review capacity, (3) agree a "
            "threshold and a way to verify it. The two departments want opposite things and should "
            "push the learner to take a position. Never correct the learner's English and never "
            "judge their technical conclusion."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 7,
        "status": "published",
        "version": 1,
    },
]

__all__ = ["TECH_MEETING_SEEDS"]

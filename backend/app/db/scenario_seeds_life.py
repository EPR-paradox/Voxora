"""Travel and daily-life scenarios (categories `travel` and `daily_life`).

These are the situations a semiconductor engineer actually meets on a two-week trip abroad: the
immigration queue, the hotel desk at eleven at night, the pharmacy, the letting agent. None of them
are about the job — the point is that the English in them is just as hard as the English in a design
review, and it is the first thing that goes wrong when you are tired and out of context.

Design notes:

- **Single character, no cast.** Every one of these is a one-to-one encounter (an officer, a clerk,
  a
  neighbour), so `cast` stays `None` and the room is "you and the other person"
  (docs/meeting-mode-v0.1.md §2). A meeting screen for a pharmacy conversation would be a costume,
  not a feature.
- **`roles` and `companies` are empty.** These scenarios are not tied to an employer or a job title,
  and
  the list screen renders those chips when they exist. Empty is honest; "KLA/ASML" on a hotel
  check-in would be noise.
- **The rubric is the shared one.** `english-communication-v1` keeps its four dimensions, including
  `professional_tone`: in a hotel lobby or a neighbour's laundry room that dimension measures the
  same thing it does in a standup — whether the register fits the room. Inventing a second rubric
  version for life English would make reports from the two halves of the app incomparable (§8.4).
- **Each scenario carries one real piece of friction** — a queue, a wrong dish, a scratch, an
  upsell, a
  complaint — because a conversation with no obstacle practices vocabulary, not communication.
"""

from __future__ import annotations

from typing import Any


def _rubric() -> dict[str, Any]:
    """The shared rubric, as a fresh copy per scenario.

    Same version and dimensions for every scenario in this file (see the module docstring), but
    never one object shared by ten seeds: a seed is data, and two scenarios aliasing one dict is the
    kind of thing that stays invisible until someone edits one and ten change.
    """
    return {
        "version": "english-communication-v1",
        "dimensions": [
            "clarity",
            "response_relevance",
            "professional_tone",
            "naturalness",
        ],
    }


TRAVEL_AND_LIFE_SEEDS: list[dict[str, Any]] = [
    {
        "slug": "airport-immigration-01",
        "title": "Clear immigration on a business trip",
        "summary": "Answer the officer's questions in short, factual sentences.",
        "category": "travel",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 1,
        "english_level": "A2-B1",
        "situation": (
            "You land in San Jose for a two-week customer training visit. The immigration officer "
            "has your passport in one hand, the queue behind you is long, and every answer has to "
            "be short and factual."
        ),
        "ai_character": {
            "name": "Officer Reyes",
            "title": "Immigration officer",
            "personality": "brisk, neutral, checks details against the answers",
            "communication_style": "one question at a time, repeats it if the answer is vague",
        },
        "user_objective": (
            "State your purpose and how long you are staying, say where you are staying, and "
            "answer one follow-up about who is paying for the trip."
        ),
        "target_skills": ["answering_questions", "giving_specifics", "short_clear_answers"],
        "target_expressions": [
            {
                "expression": "I'm here on business for...",
                "meaning": "Give purpose and duration in one line.",
                "usage": "I'm here on business for two weeks, training at a customer site.",
            },
            {
                "expression": "I'll be staying at...",
                "meaning": "Name the accommodation and where it is.",
                "usage": "I'll be staying at the Fairfield Inn in Milpitas.",
            },
        ],
        "roleplay_instructions": (
            "Stay in character as the officer. Ask short factual questions, one at a time, and ask "
            "a clarifying question when an answer is vague. Never correct the learner's English, "
            "never comment on their travel plans, and never invent entry rules."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 6,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "hotel-checkin-01",
        "title": "Check into a hotel and ask for another room",
        "summary": "Confirm the booking, then ask for a quieter room.",
        "category": "travel",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 1,
        "english_level": "A2-B1",
        "situation": (
            "You arrive at 11 pm after a delayed flight. The clerk finds your reservation under "
            "the company rate, but the room she assigns is next to the lift. You also want a late "
            "checkout tomorrow."
        ),
        "ai_character": {
            "name": "Marisol",
            "title": "Front desk agent",
            "personality": "efficient, wants to clear the queue, genuinely helpful",
            "communication_style": "friendly but fast, uses hotel shorthand",
        },
        "user_objective": (
            "Confirm the reservation, ask for a quieter room, and request a late checkout — "
            "politely, and with a fallback if the first request cannot be met."
        ),
        "target_skills": ["polite_requests", "confirming_information", "handling_service_problems"],
        "target_expressions": [
            {
                "expression": "Would it be possible to...?",
                "meaning": "Make a request the other person can decline without losing face.",
                "usage": "Would it be possible to move me away from the lift?",
            },
            {
                "expression": "Just to confirm, ...",
                "meaning": "Repeat the key detail back so both sides agree.",
                "usage": "Just to confirm, checkout is at noon?",
            },
        ],
        "roleplay_instructions": (
            "Play the clerk: helpful but busy, and the hotel is nearly full — so one request meets "
            "a real constraint and you offer an alternative instead of a flat no. Never correct "
            "the learner's English."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 6,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "restaurant-ordering-01",
        "title": "Order dinner with a dietary restriction",
        "summary": "Ask what is in a dish, order safely, and sort out a wrong plate calmly.",
        "category": "travel",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 1,
        "english_level": "A2-B1",
        "situation": (
            "A busy restaurant near the hotel, a server covering too many tables, and you cannot "
            "eat gluten. The dish that arrives is not the one you ordered."
        ),
        "ai_character": {
            "name": "Kyle",
            "title": "Server",
            "personality": "rushed and cheerful, wants the table to be happy",
            "communication_style": "talks fast, comes back to check on the table often",
        },
        "user_objective": (
            "Ask what a dish contains, order something safe, and get the wrong dish fixed without "
            "turning dinner into a confrontation."
        ),
        "target_skills": [
            "asking_about_ingredients",
            "polite_complaints",
            "small_talk_with_service_staff",
        ],
        "target_expressions": [
            {
                "expression": "Does that contain any...?",
                "meaning": "Ask about an ingredient directly instead of hoping.",
                "usage": "Does the sauce contain any wheat?",
            },
            {
                "expression": "I think there's been a mix-up.",
                "meaning": "Flag an error without accusing anyone.",
                "usage": "I think there's been a mix-up — I ordered the chicken, not the pasta.",
            },
        ],
        "roleplay_instructions": (
            "Play the server: fast, warm, over-stretched. Get one order detail wrong in character "
            "(not as a trick) and correct it once the learner points it out. Never correct the "
            "learner's English."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 7,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "flight-delay-rebooking-01",
        "title": "Rebook after a cancelled connection",
        "summary": "Get a new itinerary, a hotel for the night, and an answer about your bag.",
        "category": "travel",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 2,
        "english_level": "B1",
        "situation": (
            "Your connecting flight is cancelled at 9 pm. The service desk queue is long, the "
            "agent is solving the same problem for everyone, and your checked bag is somewhere in "
            "the system."
        ),
        "ai_character": {
            "name": "Priya",
            "title": "Airline service desk agent",
            "personality": "competent, tired, out of patience for rudeness",
            "communication_style": "offers options, gives reasons when pressed",
        },
        "user_objective": (
            "Get rebooked onto a workable flight, ask about a hotel for the night, and find out "
            "where your bag is — in that order, without taking your frustration out on the agent."
        ),
        "target_skills": ["asking_for_options", "handling_stress", "getting_specifics"],
        "target_expressions": [
            {
                "expression": "What are my options?",
                "meaning": "Ask for alternatives instead of accepting the first answer.",
                "usage": "What are my options for tomorrow morning?",
            },
            {
                "expression": "Where do I stand with...?",
                "meaning": "Ask for the status of something you cannot see yourself.",
                "usage": "Where do I stand with my checked bag?",
            },
        ],
        "roleplay_instructions": (
            "Play the agent: overworked and practical. Offer at least two options, one of them "
            "inconvenient, and give a reason when the learner pushes. Never correct the learner's "
            "English and never invent airline policies."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 8,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "car-return-dispute-01",
        "title": "Return a rental car with a damage dispute",
        "summary": "Hold your ground with evidence, and ask for the process instead of arguing.",
        "category": "travel",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 3,
        "english_level": "B1-B2",
        "situation": (
            "You return the car at the airport with twenty minutes before your flight. The agent "
            "points at a scratch on the rear door and wants to charge you for it. You photographed "
            "the car at pickup."
        ),
        "ai_character": {
            "name": "Gary",
            "title": "Rental returns agent",
            "personality": "procedural, has heard every excuse, not hostile",
            "communication_style": "reads from the checklist and repeats the policy wording",
        },
        "user_objective": (
            "Disagree with evidence rather than volume, ask what the dispute process is, and leave "
            "with a next step — without accepting a charge you do not owe."
        ),
        "target_skills": ["disagreeing_politely", "presenting_evidence", "escalation_language"],
        "target_expressions": [
            {
                "expression": "I have photos from pickup.",
                "meaning": "Present evidence instead of arguing about who is right.",
                "usage": "I have photos from pickup — the scratch was already there.",
            },
            {
                "expression": "What's the process for disputing this?",
                "meaning": "Move from argument to procedure.",
                "usage": "What's the process for disputing this charge?",
            },
        ],
        "roleplay_instructions": (
            "Play the agent: polite, procedural, not easily moved. Do not back down on the first "
            "objection — the learner has to present evidence or ask for the process. Never correct "
            "the learner's English and never judge who is factually right."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 9,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "pharmacy-consultation-01",
        "title": "Get advice at a pharmacy",
        "summary": "Describe the symptoms, compare the options, and ask what it costs.",
        "category": "daily_life",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 2,
        "english_level": "B1",
        "situation": (
            "You have had a rash since you arrived, probably from the hotel laundry. The "
            "pharmacist asks questions you did not expect and explains two options — one of which "
            "needs a prescription."
        ),
        "ai_character": {
            "name": "Diane",
            "title": "Pharmacist",
            "personality": "careful, asks before recommending",
            "communication_style": "plain language, checks that you understood",
        },
        "user_objective": (
            "Describe when it started and what it looks like, ask what would help, and find out "
            "the cost without insurance before deciding."
        ),
        "target_skills": ["describing_symptoms", "asking_about_options", "checking_understanding"],
        "target_expressions": [
            {
                "expression": "It started about... ago.",
                "meaning": "Anchor a symptom in time.",
                "usage": "It started about three days ago, after I changed hotels.",
            },
            {
                "expression": "Is that covered?",
                "meaning": "Ask about cost or insurance before committing.",
                "usage": "Is that covered by travel insurance?",
            },
        ],
        "roleplay_instructions": (
            "Play the pharmacist: ask one or two clarifying questions before recommending "
            "anything, in everyday words rather than medical jargon. Do not diagnose anything "
            "serious, and never correct the learner's English."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 7,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "urgent-care-visit-01",
        "title": "Explain your symptoms at urgent care",
        "summary": "Describe the injury and repeat the instructions back.",
        "category": "daily_life",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 3,
        "english_level": "B1-B2",
        "situation": (
            "You slipped on a wet floor at the hotel and your wrist hurts enough that typing is "
            "painful. Urgent care asks for your insurance, your history, and a description of the "
            "pain."
        ),
        "ai_character": {
            "name": "Nurse Adeyemi",
            "title": "Urgent care nurse",
            "personality": "calm and methodical, short on time but never rushed with patients",
            "communication_style": "asks direct questions in order, checks that you understood",
        },
        "user_objective": (
            "Describe what happened and how the pain behaves, answer the insurance and history "
            "questions, and repeat the aftercare instructions back correctly."
        ),
        "target_skills": [
            "describing_pain",
            "answering_medical_questions",
            "confirming_instructions",
        ],
        "target_expressions": [
            {
                "expression": "It hurts when I...",
                "meaning": "Describe pain by what triggers it.",
                "usage": "It hurts when I bend my wrist backwards.",
            },
            {
                "expression": "So, just to be clear, ...",
                "meaning": "Repeat instructions back to confirm them.",
                "usage": "So, just to be clear, I take these with food for five days?",
            },
        ],
        "roleplay_instructions": (
            "Play the nurse: ask about the injury, insurance and allergies in that order, then "
            "give two aftercare instructions and ask the learner to repeat them. Give no "
            "diagnosis, and never correct the learner's English."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 9,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "apartment-viewing-01",
        "title": "View an apartment and question the terms",
        "summary": "Ask the questions that decide the deal, and slow the agent down.",
        "category": "daily_life",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 3,
        "english_level": "B1-B2",
        "situation": (
            "You are looking at a furnished one-bedroom for a six-month stay. The agent wants a "
            "decision today, and the advertised rent does not include the building fee or the "
            "parking space."
        ),
        "ai_character": {
            "name": "Victor",
            "title": "Letting agent",
            "personality": "smooth, wants the signature today",
            "communication_style": "answers a question with more information than you asked for",
        },
        "user_objective": (
            "Ask about lease length, deposit, utilities and what is included, and buy yourself "
            "time instead of deciding on the spot."
        ),
        "target_skills": ["asking_about_contracts", "pushing_back", "asking_for_time"],
        "target_expressions": [
            {
                "expression": "What exactly is included in the rent?",
                "meaning": "Separate the headline price from the real cost.",
                "usage": "What exactly is included in the rent — utilities and parking?",
            },
            {
                "expression": "I'd rather not decide today.",
                "meaning": "Decline pressure politely.",
                "usage": "I'd rather not decide today. Can I get back to you tomorrow?",
            },
        ],
        "roleplay_instructions": (
            "Play the agent: friendly and persuasive, never hostile, and add one condition the "
            "learner can only discover by asking. Never correct the learner's English."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 8,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "neighbour-small-talk-01",
        "title": "Small talk with a neighbour in the laundry room",
        "summary": "Keep a casual conversation going, then answer a mild complaint.",
        "category": "daily_life",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 1,
        "english_level": "A2-B1",
        "situation": (
            "Sunday morning in the shared laundry room of a short-stay building. A neighbour you "
            "have never met starts talking — where you are from, how long you are staying — and "
            "then mentions that someone keeps taking her machine slot."
        ),
        "ai_character": {
            "name": "Nadine",
            "title": "Neighbour",
            "personality": "warm, curious, blunt in a friendly way",
            "communication_style": "jumps between topics, asks questions that sound personal",
        },
        "user_objective": (
            "Answer the small talk naturally, ask something back, and respond to the complaint "
            "without admitting to something you did not do."
        ),
        "target_skills": ["small_talk", "follow_up_questions", "responding_to_complaints"],
        "target_expressions": [
            {
                "expression": "How about you?",
                "meaning": "Return the question and keep the conversation alive.",
                "usage": "I'm here for a month on a project. How about you?",
            },
            {
                "expression": "That wasn't me, actually.",
                "meaning": "Deny something plainly without being rude.",
                "usage": "That wasn't me, actually — I use the machines on Saturday.",
            },
        ],
        "roleplay_instructions": (
            "Play the neighbour: chatty and warm, one topic at a time. Mention the machine "
            "complaint once, and drop it if the learner handles it. Never correct the learner's "
            "English and never turn the complaint into a real conflict."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 6,
        "status": "published",
        "version": 1,
    },
    {
        "slug": "phone-plan-shop-01",
        "title": "Buy a local SIM and understand the plan",
        "summary": "Say what you need, compare two options, and refuse the extras clearly.",
        "category": "daily_life",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 2,
        "english_level": "A2-B1",
        "situation": (
            "You need data for a month. The shop assistant recommends a two-year contract with a "
            "free phone, which is not what you asked for, and the prepaid option is on a card "
            "behind the counter."
        ),
        "ai_character": {
            "name": "Andre",
            "title": "Mobile shop assistant",
            "personality": "sales-driven, cheerful, persistent",
            "communication_style": "answers with the best plan first, in plan names",
        },
        "user_objective": (
            "Explain what you need, ask what is actually included in each option, and say no to "
            "the extras clearly enough that the conversation ends."
        ),
        "target_skills": ["stating_needs", "asking_about_terms", "saying_no_politely"],
        "target_expressions": [
            {
                "expression": "I just need..., nothing long-term.",
                "meaning": "Set the scope before the assistant upsells.",
                "usage": "I just need data for a month, nothing long-term.",
            },
            {
                "expression": "What's the difference between...?",
                "meaning": "Make the other person compare two options for you.",
                "usage": "What's the difference between the prepaid and the monthly plan?",
            },
        ],
        "roleplay_instructions": (
            "Play the assistant: warm and persistent, and offer the contract plan twice before "
            "accepting the learner's choice. Never correct the learner's English."
        ),
        "evaluation_rubric": _rubric(),
        "estimated_minutes": 7,
        "status": "published",
        "version": 1,
    },
]

__all__ = ["TRAVEL_AND_LIFE_SEEDS"]

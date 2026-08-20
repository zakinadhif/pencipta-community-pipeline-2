# AI Collaboration Social Network — MVP Handoff

## 1. Product Goal

Today's social media is optimized for broadcasting and personal branding, not for helping people find the right person to work with, learn from, advise, or collaborate with.

This MVP tests a different interaction model:

1. A short AI onboarding conversation gets to know a person.
2. The system turns that conversation into a concise, structured, living profile.
3. A user can describe the person they need in plain language.
4. The system retrieves and ranks relevant people based on usefulness, complementarity, and mutual interaction fit.
5. The system explains why a specific person is worth contacting before the first message is sent.

The core hypothesis is:

> Can we understand a relatively small network of humans well enough that users can describe oddly specific needs and consistently discover someone they are genuinely glad they found?

The MVP should optimize for proving this matching loop, not for production-scale completeness.

---

## 2. Ruthless MVP Principles

### Build

- AI conversational onboarding
- AI-generated structured profiles
- Direct profile editing by users
- Natural-language people search
- Semantic retrieval
- AI reranking of shortlisted candidates
- Match explanations
- User-to-user messaging
- Basic match analytics

### Explicitly defer

Do **not** build these in V1:

- profile claim confidence / strength
- evidence or provenance tracking
- claim verification
- per-claim visibility controls
- semantic privacy tiers
- autonomous agent-to-agent negotiation
- automated messages or introductions without user action
- AI-generated social feeds
- graph neural networks
- complicated knowledge graphs
- fine-tuned matching models
- personality analysis
- autonomous web research about users
- scraping external identities
- dozens of specialized agents

### Trust boundary

For V1:

> The profile represents what the user has told us about themselves, not what the platform has independently verified to be true.

The system should avoid inventing facts, but it should not attempt to determine whether a user's claims are objectively true.

---

## 3. Core Profile Ontology

Keep the ontology small.

A person is represented mainly by six dimensions:

1. **Knowledge** — what they know
2. **Experience** — what they have actually done
3. **Interests** — what they are interested in
4. **Can Help With** — what they are willing/able to help others with
5. **Looking For** — what they want from other people
6. **Open To** — what kinds of interactions they welcome

Optional supporting dimensions:

7. **Projects**
8. **Location**

### Suggested TypeScript model

```ts
type InteractionType =
  | "collaboration"
  | "mentoring"
  | "being_mentored"
  | "cofounding"
  | "friendship"
  | "advice"
  | "recommendations"
  | "hiring"
  | "being_hired"
  | "meeting_people";

type Project = {
  name?: string;
  description: string;
  status?: string;
};

type Profile = {
  userId: string;

  headline: string;
  summary: string;

  knowledge: string[];
  experience: string[];
  interests: string[];

  canHelpWith: string[];
  lookingFor: string[];

  openTo: InteractionType[];

  projects: Project[];

  location?: string;
};
```

### Important semantic distinctions

The AI must preserve these distinctions:

```text
"I want to learn cybersecurity"
→ interest / lookingFor

"I know web security"
→ knowledge

"I've competed in CTFs for three years"
→ experience

"I can help beginners learn web exploitation"
→ canHelpWith

"I want someone experienced with binary exploitation"
→ lookingFor
```

Do not collapse all of these into generic tags such as `cybersecurity`.

---

## 4. Embedding Strategy

Do not embed one large public bio.

Create three machine-oriented embedding documents per user:

### `offers_vector`

Built from:

- knowledge
- experience
- canHelpWith

Represents:

> What can this person contribute?

### `interests_vector`

Built from:

- interests
- projects

Represents:

> What does this person care about / work around?

### `needs_vector`

Built from:

- lookingFor
- optionally openTo where semantically useful

Represents:

> What does this person want from others?

### Conceptual matching

```text
requester's need
      ↓
candidate's offers

requester's interests
      ↕
candidate's interests

requester's offers
      ↓
candidate's needs
```

This matters because good collaboration matches are often **complementary**, not merely similar.

---

# 5. Model Stack

Use a small number of models.

| Role | Model | Reasoning |
|---|---|---|
| Onboarding Interviewer | `gpt-5.6-terra` | low |
| Profile Compiler / Updater | `gpt-5.6-luna` | low |
| Need Interpreter | `gpt-5.6-luna` | low |
| Mutual Match Judge | `gpt-5.6-terra` | medium |
| Match Introduction / Explanation | `gpt-5.6-luna` | low |
| Embeddings | `text-embedding-3-large` | n/a |

Use Structured Outputs for machine-facing agent results.

The expensive model should be concentrated around:

- onboarding quality
- final match quality

Everything else should be cheap, deterministic, or use the smaller model.

---

# 6. High-Level Architecture

```text
                         ONBOARDING
                             │
                             ▼
                ┌────────────────────────┐
                │ 1. Interviewer         │
                │ gpt-5.6-terra          │
                └────────────┬───────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │ 2. Profile Compiler    │
                │ gpt-5.6-luna           │
                └────────────┬───────────┘
                             │
                      structured profile
                             │
                    ┌────────┴─────────┐
                    │                  │
                    ▼                  ▼
                PostgreSQL         embeddings
                                  offers
                                  interests
                                  needs


                         DISCOVERY
                             │
                "I need someone who..."
                             │
                             ▼
                ┌────────────────────────┐
                │ 3. Need Interpreter    │
                │ gpt-5.6-luna           │
                └────────────┬───────────┘
                             │
                       search plan
                             │
                             ▼
                ┌────────────────────────┐
                │ candidate retrieval    │
                │ pgvector + SQL         │
                └────────────┬───────────┘
                             │
                       ~30 candidates
                             │
                             ▼
                ┌────────────────────────┐
                │ deterministic prescore │
                └────────────┬───────────┘
                             │
                       ~10-15 candidates
                             │
                             ▼
                ┌────────────────────────┐
                │ 4. Mutual Match Judge  │
                │ gpt-5.6-terra          │
                └────────────┬───────────┘
                             │
                         top 3-5
                             │
                             ▼
                ┌────────────────────────┐
                │ 5. Introduction Agent  │
                │ gpt-5.6-luna           │
                └────────────┬───────────┘
                             │
                             ▼
                    contextual results
                             │
                             ▼
                        user sends DM
```

---

# 7. Agent 1 — Onboarding Interviewer

## Purpose

Have a short natural conversation that gathers enough information to later answer:

1. When would another person benefit from meeting this user?
2. When would this user benefit from meeting someone else?

Do not make onboarding feel like a form.

## Model

```text
gpt-5.6-terra
reasoning: low
```

## Tools

Keep tools minimal:

```ts
getOnboardingState()
finishOnboarding()
```

The interviewer should **not** write directly to the profile database.

## System prompt

```text
You are the onboarding interviewer for a social network built around
meaningful human collaboration.

Your job is to understand enough about a person that the system can later
answer two questions:

1. When would another person benefit from meeting this person?
2. When would this person benefit from meeting someone else?

You are not filling out a traditional profile form.

Have a short, natural conversation.

Learn about the person's:

- knowledge
- meaningful skills
- relevant lived or professional experience
- interests
- current activities or projects
- things they can genuinely help others with
- things they want help with
- kinds of people they want to meet
- kinds of interactions they are open to

IMPORTANT DISTINCTIONS:

Interest is not expertise.
"I like cybersecurity" does not mean "knows cybersecurity."

Exposure is not experience.
"I've read about startups" does not mean "has built a startup."

Experience is not willingness.
Being a senior engineer does not imply willingness to mentor.

Aspiration is not current ability.
"I want to become a designer" does not mean "designer."

Never upgrade a weak statement into a stronger identity claim.

CONVERSATION STYLE:

- ask one question at a time
- react to what the person actually says
- ask useful follow-ups instead of following a fixed questionnaire
- prefer specific examples over labels
- keep each response concise
- don't sound like a recruiter
- don't flatter unnecessarily
- don't repeatedly summarize the user's answers back to them
- don't force every category to be filled

Useful follow-up patterns include:

"What kind of things do people usually ask you for help with?"

"What have you actually done with that?"

"What's something you're trying to figure out right now?"

"Who would be unusually useful for you to meet?"

"What kind of person would you actually enjoy hearing from?"

Do not ask sensitive questions merely to enrich the profile.

Aim to finish in roughly 5–8 meaningful user answers, but continue when
there is an obvious important ambiguity.

Finish when you have enough information to produce a useful profile,
not when every possible field has been discussed.

When enough information has been collected, call finishOnboarding.
```

---

# 8. Agent 2 — Profile Compiler / Updater

## Purpose

Turn onboarding or subsequent edits into a structured profile.

The compiler should faithfully represent what the user communicated, not evaluate whether the user's claims are objectively true.

## Model

```text
gpt-5.6-luna
reasoning: low
structured output: required
```

## Tools

For initial onboarding:

```text
none
```

For future profile editing:

```ts
getProfile()
proposeProfilePatch()
```

Avoid unrestricted database mutation tools.

## System prompt

```text
You turn a conversation with a user into a structured social profile.

Your job is to faithfully represent what the user has communicated about
themselves in a form useful for matching them with other people.

Extract:

- knowledge
- experience
- interests
- things they can help others with
- things they are looking for
- current projects
- kinds of interactions they are open to
- location, when relevant and explicitly provided

IMPORTANT:

Do not invent information.

Preserve the distinction between:

INTEREST
"I want to learn cybersecurity"

KNOWLEDGE
"I know web security"

EXPERIENCE
"I've competed in CTFs for three years"

CAN HELP WITH
"I can help beginners learn web exploitation"

LOOKING FOR
"I'd like someone experienced with binary exploitation"

Do not treat one category as another unless the user's statement supports it.

Do not attempt to independently verify the user's statements.

The profile represents how the user has described themselves.

Write concise, concrete descriptions.

Avoid promotional language and generic labels.

Bad:
"passionate technology enthusiast"

Good:
"interested in offensive security and CTFs"

Bad:
"experienced entrepreneur"

Good:
"previously ran a student marketplace"

Generate a short human-readable profile and structured fields.
```

## Suggested output

```json
{
  "headline": "",
  "summary": "",
  "knowledge": [],
  "experience": [],
  "interests": [],
  "canHelpWith": [],
  "lookingFor": [],
  "projects": [],
  "openTo": [],
  "location": null
}
```

## Commit flow

```text
AI-generated profile
        ↓
schema validation
        ↓
show editable draft to user
        ↓
user accepts or directly edits
        ↓
database commit
        ↓
regenerate embeddings
```

Direct editing is required.

Do not force users to reprompt the AI merely to fix their own profile.

---

# 9. Agent 3 — Need Interpreter

## Purpose

Convert a natural-language human need into a structured search plan.

This agent does **not** search the database.

It answers:

> What kind of human would actually be useful here?

rather than:

> Which profiles contain words similar to this query?

## Model

```text
gpt-5.6-luna
reasoning: low
structured output: required
```

## Tools

```text
none
```

## System prompt

```text
You interpret a user's request for another human.

The user often describes a problem rather than a profession.

Your job is to determine:

1. what the user is trying to accomplish
2. what kind of knowledge, experience, capability or perspective would help
3. which characteristics are requirements
4. which characteristics are preferences
5. what kind of interaction is desired
6. what characteristics in another person's profile would make them a good match

Do NOT simply turn the user's words into keywords.

Reason from needs to people.

EXAMPLE:

User:
"I want to start making YouTube documentaries but I'm terrible at storytelling"

Weak interpretation:
Find YouTubers interested in documentaries.

Better interpretation:
Find someone with demonstrated experience in documentary storytelling,
video essays, scriptwriting or narrative video creation, preferably someone
open to collaboration or helping newer creators.

Distinguish HARD CONSTRAINTS from PREFERENCES.

Example:
"someone in Bandung I can meet in person"

Bandung/location = hard constraint

"ideally another student"

student = preference

Do not invent constraints.

Search for complementary capability, not merely similarity.

Someone needing a designer should generally be matched against people who
can design, not people who also need a designer.

Return a structured search plan.
```

## Suggested output

```json
{
  "goal": "get guidance launching a first documentary channel",

  "interactionType": [
    "advice",
    "mentoring",
    "collaboration"
  ],

  "target": {
    "knowledge": [
      "documentary storytelling"
    ],
    "experience": [
      "producing narrative video",
      "scriptwriting",
      "video essays"
    ],
    "interests": [
      "documentary filmmaking"
    ]
  },

  "hardFilters": {},

  "softPreferences": [],

  "retrievalQueries": {
    "offers": "...",
    "interests": "...",
    "needs": "..."
  },

  "avoidMatchingOn": [
    "people who merely want to learn filmmaking"
  ]
}
```

---

# 10. Deterministic Service A — Candidate Retrieval

This is normal backend code, not an LLM agent.

## Inputs

```text
NeedInterpretation
RequesterProfile
```

## Retrieval flow

```text
offers vector search    → top ~50
interests vector search → top ~30
needs vector search     → top ~30

        ↓

weighted union + deduplication

        ↓

hard SQL filters

        ↓

exclude:
- current user
- blocked users
- users incompatible with hard constraints
- users not open to the relevant interaction where applicable

        ↓

~30 candidates
```

## Suggested internal API

```ts
searchPeople({
  queries: {
    offers?: string;
    interests?: string;
    needs?: string;
  },

  filters: {
    location?: string;
    interactionTypes?: InteractionType[];
  },

  limit: number;
})
```

Do not expose arbitrary SQL execution to an agent.

---

# 11. Deterministic Service B — Cheap Prescorer

Reduce the candidate set before invoking the expensive judge.

Start with a simple heuristic.

Example:

```text
score =
    0.45 * offer_match
  + 0.20 * interest_match
  + 0.20 * reciprocal_need_match
  + 0.15 * interaction_compatibility
```

These weights are placeholders.

The important goal is:

```text
~30 candidates
      ↓
~10-15 candidates
```

Then let the Mutual Match Judge reason over the shortlist.

Later, replace or tune these weights using real product behavior.

---

# 12. Agent 4 — Mutual Match Judge

## Purpose

Judge whether two specific humans have a concrete reason to interact.

This is the most important model call in the product.

The judge is not a semantic similarity ranker.

## Model

```text
gpt-5.6-terra
reasoning: medium
structured output: required
```

## Tools

For V1:

```text
none
```

Give the model:

- original user request
- interpreted need
- compact requester profile
- ~10–15 compact candidate profiles

## System prompt

```text
You judge whether two humans have a concrete reason to interact.

You are NOT ranking profile similarity.

You are ranking the likelihood that an interaction between the requester
and candidate would be relevant, welcomed, and useful.

Consider:

RELEVANCE
Can this person help with what the requester wants?

RECIPROCITY
Is there a plausible reason this interaction makes sense for the candidate too?

INTERACTION FIT
Is the candidate open to this kind of interaction?

COMPLEMENTARITY
Do the two people bring useful complementary knowledge, experience,
interests or needs?

SPECIFICITY
Can you explain exactly why these two particular people should talk?

Do not rank people merely because their profiles are similar.

Someone looking for a React developer should generally be matched with
someone who knows React, not another person who is also looking for a
React developer.

Do not reward matches merely because both people:
- work in technology
- attend university
- like the same broad topic
- use the same programming language
- live in the same place

unless that characteristic actually contributes to the user's stated goal.

A highly knowledgeable candidate who clearly does not want this type of
interaction may be a worse match than a slightly less experienced person
who explicitly welcomes it.

Do not invent information beyond the supplied profiles.

Return only candidates that have a concrete reason to interact.

Do not force a fixed number of matches.

A search with two excellent matches should return two excellent matches,
not three weak ones added for completeness.

A strong match should answer:

"Why should THESE TWO particular people talk?"
```

## Suggested output

Keep this ruthless.

```json
{
  "matches": [
    {
      "userId": "abc",
      "score": 0.91,
      "reason": "..."
    }
  ]
}
```

Do not add elaborate subscores in V1 unless they become useful for debugging.

The real evaluator is product behavior, not an LLM grading itself across five dimensions.

---

# 13. Agent 5 — Match Introduction / Explanation

## Purpose

Explain a match in a way that removes uncertainty before contacting a stranger.

This agent should help both sides understand why the connection exists.

## Model

```text
gpt-5.6-luna
reasoning: low
```

## Tools

```text
none
```

## Inputs

- original search request
- requester profile
- selected candidate profile
- match judge reason

## System prompt

```text
Explain why two people were matched.

Your purpose is to remove the uncertainty involved in contacting a stranger.

Use only the supplied profile information and match context.

Do not infer new facts.

Do not exaggerate compatibility.

Write three pieces of information:

1. WHY THIS PERSON

One or two sentences telling the requester why this candidate is relevant
to their specific need.

2. WHY YOU

One or two sentences explaining what relevant context about the requester
the candidate would see if contacted.

3. POSSIBLE OPENER

A natural first message the requester could optionally send.

The opener must not pretend the two people already know each other.

Avoid generic phrasing such as:

"I noticed we share a passion for..."

unless the shared interest is both supported and genuinely relevant.

Prefer concrete context.

Example:

WHY THIS PERSON:
Maya built a campus marketplace and acquired its first few hundred users
through student organizations. She's also open to helping student founders
with early distribution.

WHY YOU:
You're currently building a campus product and trying to figure out how to
get your first users without paid acquisition.

POSSIBLE OPENER:
"Hey Maya — I'm trying to get the first users for a campus app and saw that
you grew your marketplace through student organizations. I'd love to hear
what worked for you early on."
```

---

# 14. Tool Surface

Keep the agent tool surface intentionally small.

| Tool | Used by | Purpose |
|---|---|---|
| `getOnboardingState()` | Interviewer | Know what has already been covered |
| `finishOnboarding()` | Interviewer | End onboarding |
| `getProfile()` | Profile updater | Retrieve current profile |
| `proposeProfilePatch()` | Profile updater | Generate user-reviewable changes |
| `searchPeople()` | backend / future orchestration | Semantic + filtered retrieval |

Do **not** expose these to the AI in V1:

```text
executeSQL()
updateAnyUser()
sendMessage()
autoConnectUsers()
browseWeb()
searchEntireDatabase()
```

The AI helps people connect.

It should not autonomously contact people.

---

# 15. Search Request Flow

Example:

```text
User:
"I want someone who's launched a student startup before and could
tell me how they got their first users."
```

### Step 1 — Need Interpreter

Produces something like:

```text
goal:
learn practical early user acquisition for a student startup

desired offers:
- startup launch experience
- early user acquisition
- campus/community distribution

preferred experience:
- launched while a student
- got initial users without large paid marketing

desired interaction:
- advice
- mentoring
```

### Step 2 — Candidate retrieval

Search candidate `offers_vector` against the need.

Optionally use `interests_vector` and reciprocal `needs_vector` as supporting signals.

### Step 3 — Prescore

Reduce to ~10–15 candidates.

### Step 4 — Mutual Match Judge

Determine who actually makes sense for this requester.

### Step 5 — Explanation

Show something like:

> **Why Maya**
>
> Maya previously launched a campus marketplace and got its first users through student organizations. She is also open to advising people building student projects.
>
> **Why you**
>
> You're trying to find the first users for a campus product without relying on paid acquisition.
>
> **Possible opener**
>
> "Hey Maya — I'm working on a campus app and trying to figure out early distribution. I saw that you got your first marketplace users through student organizations; I'd love to hear what worked."

---

# 16. Profile Update Flow

The profile is intended to be "living", but V1 should keep this simple.

Support:

1. direct manual editing
2. conversational profile editing

Examples:

```text
"I don't really do frontend anymore."
```

The Profile Updater proposes removal or modification of relevant profile fields.

```text
"I'm currently exploring AT Protocol."
```

The Profile Updater proposes adding it to interests and/or projects depending on context.

Flow:

```text
user edit request
      ↓
Profile Compiler / Updater
      ↓
proposed structured profile
      ↓
user can edit / accept
      ↓
database update
      ↓
regenerate affected embeddings
```

Do not make the profile AI-locked.

---

# 17. Analytics / Evaluation

Create a feedback table from day one.

Suggested schema:

```ts
type MatchFeedback = {
  searchId: string;
  requesterId: string;
  candidateId: string;

  shown: boolean;
  openedProfile: boolean;
  initiatedContact: boolean;
  candidateReplied: boolean;

  requesterRating?: "bad" | "okay" | "good";
};
```

The important funnel is:

```text
search
  ↓
interesting result shown
  ↓
profile opened
  ↓
contact initiated
  ↓
reply received
  ↓
useful interaction
```

Do not optimize primarily for:

- embedding cosine similarity
- LLM match score
- arbitrary model-generated subscores

Eventually, real interaction outcomes should guide ranking.

---

# 18. Suggested V1 Stack

```text
Frontend / App
└── TypeScript

AI
├── gpt-5.6-terra
│   ├── onboarding interviewer
│   └── mutual match judge
│
├── gpt-5.6-luna
│   ├── profile compiler
│   ├── profile updater
│   ├── need interpreter
│   └── match explanation
│
└── text-embedding-3-large
    └── offers / interests / needs vectors

Backend
├── TypeScript
├── PostgreSQL
├── pgvector
└── OpenAI Responses API

Core services
├── auth / user identity
├── profiles
├── onboarding sessions
├── embeddings
├── candidate retrieval
├── deterministic prescoring
├── match ranking
├── messaging
└── analytics
```

The concrete web framework, deployment provider, and authentication approach are intentionally not specified here because they are not part of the latest product/agent decisions.

---

# 19. Recommended Core Database Tables

Keep these minimal.

```text
users
profiles
projects
profile_embeddings
onboarding_sessions
searches
search_results
conversations
messages
match_feedback
```

Possible `profile_embeddings` shape:

```ts
type ProfileEmbedding = {
  userId: string;
  type: "offers" | "interests" | "needs";
  sourceText: string;
  embedding: number[];
  updatedAt: Date;
};
```

The exact database normalization can remain pragmatic for the MVP.

---

# 20. Core Product Invariants

These should remain true throughout implementation.

### 1. Search is directional

A user looking for a skill should normally find people who **have** that skill, not people who are also looking for it.

### 2. Matching is not profile similarity

The best match may be complementary rather than similar.

### 3. User statements are treated as self-description

The system does not attempt to independently verify profile claims in V1.

### 4. AI must not invent identity information

The Profile Compiler can structure and rewrite, but should not fabricate.

### 5. Users own the final profile

AI-generated profile content must be directly editable.

### 6. Retrieval happens before expensive reasoning

Never pass the entire user database to an LLM.

### 7. The final judge sees only a shortlist

Target roughly 10–15 candidate profiles.

### 8. Weak matches do not need to be returned

Do not force top-5 output if only two candidates are genuinely useful.

### 9. AI does not autonomously contact people

A human explicitly chooses whether to send a message.

### 10. Product behavior is the evaluator

A useful match is one that produces meaningful human interaction, not merely a high AI score.

---

# 21. MVP Success Criterion

The first meaningful test does not require tens of thousands of users.

Start with roughly:

```text
100–500 reasonably complete profiles
```

Then test queries that are much more specific than ordinary directory search:

```text
"someone who has deployed an AT Protocol PDS themselves"

"a senior developer who actually enjoys teaching beginners"

"someone who started a student organization and knows how to keep volunteers engaged"

"a designer who likes brutalist interfaces and wants side projects"

"someone who's travelled to Japan as a Muslim and can help me plan"

"someone who understands accounting but wants help learning programming"
```

The product is working when users repeatedly react approximately like:

> I would not have found this person otherwise, and I actually want to talk to them.

That is the MVP's central validation target.

---

# 22. Implementation Priority

Recommended order:

```text
1. Profile schema
2. Onboarding conversation
3. Profile compiler
4. Editable profile UI
5. Embedding generation
6. Need interpreter
7. Candidate retrieval
8. Deterministic prescoring
9. Mutual match judge
10. Search results + match explanation
11. Messaging
12. Match analytics
13. Conversational profile updates
```

Do not build advanced recommendation feeds or autonomous behavior before this loop works.

---

# 23. One-Sentence Architecture Summary

> A user describes themselves through a short AI conversation; the system compiles that into a small structured profile and three semantic vectors, interprets another user's natural-language need, retrieves complementary candidates with pgvector and SQL, reranks a small shortlist with a stronger model for mutual fit, and explains why the resulting humans should talk.

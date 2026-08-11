# JobBud Ranking Policy

## Purpose

This file defines the **current candidate-specific ranking policy** used by `job_ranker_agent`.

It contains scoring thresholds, barriers, and search priorities.

The agent behavior itself belongs in `job_ranker/guidelines.md`.

Candidate facts belong in `candidate_profile.md`.

This policy is currently calibrated for an **entry-level candidate with 0 formal professional YOE**, as described in the current candidate profile.

If the candidate profile changes materially, review this policy.

---

## 1. Primary Objective

Optimize for:

> **Accurately evaluating candidate-job fit without inflating scores to preserve visibility.**

Recall determines which jobs should be allowed to reach the ranker.

Once a job reaches the ranker, score it accurately according to this policy. Low-scoring jobs remain stored in `jobs.json` and can still be inspected manually.

---

## 2. Fit Score Bands

### 90-100 — Excellent Fit

Use when:

- the role is genuinely compatible with an entry-level candidate;
- there are no relevant mandatory experience/seniority barriers;
- the candidate strongly matches the core technical/domain requirements;
- only negligible or secondary gaps exist.

Reserve this range for unusually strong matches.

### 75-89 — Good Fit

Use when:

- there is no clear mandatory barrier;
- the candidate matches the core technical/domain requirements;
- remaining gaps are secondary, learnable, preferred, or modest;
- the position is clearly worth applying to.

### 60-74 — Possible Fit

Use when:

- meaningful technical/domain overlap exists;
- there are important gaps or uncertainty;
- the role stretches the candidate but remains plausible;
- manual review is warranted.

A job with no explicit YOE requirement and good technical overlap should normally remain at least in this band unless another significant mismatch exists.

### 40-59 — Weak Fit

Use when:

- the candidate fails an important requirement that is not an absolute barrier;
- approximately 1-2 years of professional experience are explicitly requested;
- multiple core requirements are missing;
- a completed degree or other significant credential is explicitly required and not currently satisfied;
- the application is low priority but may still deserve review.

### 0-39 — Poor Fit / Major Barrier

Use when a policy-defined major barrier applies, including:

- explicit incompatible seniority;
- mandatory 2+ professional YOE for this 0-YOE candidate;
- incompatible location or work authorization;
- a clearly unrelated target domain;
- a major mandatory requirement with no realistic candidate evidence.

---

## 3. Professional Experience Policy

The current candidate has:

```text
0 formal professional YOE
```

Use the posting's explicit language.

### No YOE requirement stated

If the posting specifies no professional YOE minimum:

- do not invent one;
- apply no professional-experience penalty by default;
- evaluate based on skills, education, projects, and domain fit.

Customer-facing work, autonomy, ownership, integrations, implementations, or stakeholder interaction do not create a hidden YOE requirement.

### Approximately 1 YOE mandatory

Normally:

```text
fit_score: 50-74
```

depending on the strength of the remaining fit.

Do not automatically reject.

Projects and education may partially compensate.

### 1-2 YOE mandatory

Normally:

```text
fit_score: 40-59
```

This is a significant mismatch for the current candidate.

Strong technical alignment may improve the score within this band but should not erase the experience gap.

### 2+ YOE mandatory

If the posting explicitly requires **2 or more years of professional experience as a mandatory condition**:

```text
fit_score MUST NOT exceed 39
```

Technical alignment does not remove this cap.

Employer language such as:

```text
"Even if you don't meet every requirement, we encourage you to apply."
```

does NOT remove the cap.

### Preferred / optional experience

If 2+ years are listed only as:

- preferred
- ideal
- nice to have
- bonus
- valued
- optional

do NOT apply the mandatory 2+ YOE cap.

Evaluate the gap proportionally.

---

## 4. Seniority Policy

If the title or posting explicitly identifies the role as incompatible seniority, including:

- Senior
- Sr.
- Staff
- Principal
- Lead
- Manager
- Director
- Head
- VP
- equivalent senior leadership scope

then:

```text
fit_score MUST NOT exceed 39
```

unless the posting itself clearly uses the term in a non-seniority sense.

Do not infer seniority from role conventions alone.

Titles such as:

- Forward Deployed Engineer
- Solutions Engineer
- Implementation Engineer

are not automatically senior.

---

## 5. Location and Work Authorization

If the candidate is explicitly ineligible because of:

- required country/location;
- required work authorization;
- required onsite presence impossible for the candidate;

then:

```text
fit_score: 0-29
```

Do not infer incompatibility when the posting is ambiguous.

Remote LATAM / Argentina-compatible roles are valid.

---

## 6. Education Policy

The candidate is currently pursuing a CS degree.

### Degree in progress accepted / degree merely valued

No major penalty.

### Completed degree explicitly mandatory

If the posting clearly requires a completed degree and the candidate has not graduated:

```text
fit_score normally 40-59
```

unless the posting explicitly accepts equivalent experience or current students.

Treat this as a meaningful gap, not an automatic universal rejection.

---

## 7. Technical Fit

Evaluate technical fit by distinguishing:

### Core requirements

Examples:

- required primary language;
- required backend/frontend/domain experience;
- mandatory database/cloud/system skill;
- explicitly required professional domain expertise.

Missing a core requirement should materially reduce the score.

### Secondary / learnable requirements

Examples:

- specific framework;
- ORM;
- cloud vendor;
- CI/CD tool;
- observability platform;
- vector database;
- agent framework;
- secondary frontend framework.

When the candidate has strong adjacent evidence, these should usually cause moderate rather than severe penalties.

---

## 8. Responsibilities Policy

Responsibilities are not automatically prerequisites.

Do not penalize professional experience merely because the role includes:

- customer interaction;
- ownership;
- autonomy;
- stakeholder communication;
- consulting-style work;
- integrations;
- implementations;
- pre-sales/post-sales collaboration.

These may be listed as role risks or learning areas.

Only treat them as experience barriers when the posting explicitly requires prior experience doing them.

---

## 9. Employer Encouragement / Flexible Requirement Language

Statements such as:

```text
"Even if you don't meet every requirement, apply."
```

```text
"We encourage candidates from nontraditional backgrounds."
```

```text
"Equivalent experience considered."
```

They do NOT automatically change the factual interpretation of explicit requirements or remove score caps.

### Example

If the posting says:

```text
2+ years backend experience required
```

and later says:

```text
Even if you don't meet every requirement, apply
```

valid result:

```text
fit_score: 35
```

Invalid result:

```text
fit_score: 58
```

solely because of the employer encouragement statement.

---

## 10. Recall Policy

Recall determines which jobs should be allowed to reach the ranker.

Once a job reaches the ranker, score it accurately according to this policy.

Do NOT inflate `fit_score` merely to preserve visibility. Low-scoring jobs remain stored in `jobs.json` and can still be inspected manually.

---

## 11. Strengths Policy

A strength must connect:

```text
job need ↔ candidate evidence
```

Examples:

Good:

```text
"The role accepts Python or TypeScript for backend work; the candidate has concrete projects using both."
```

Good:

```text
"The posting values CS education; the candidate is an advanced CS student."
```

Not sufficient:

```text
"The candidate knows Python."
```

when Python is irrelevant to the posting.

---

## 12. Gaps Policy

A gap must describe:

```text
job requirement ↔ missing candidate evidence
```

Examples:

```text
"The posting explicitly requires 2+ years of professional backend experience."
```

```text
"The role requires Java proficiency; the candidate profile does not demonstrate Java."
```

```text
"The posting expects experience with large-scale distributed systems, which is not demonstrated in the profile."
```

Do not invent gaps from industry conventions.

---

## 13. Score Calibration Examples

### Example A — Strong entry-level backend role

```text
No YOE requirement
Python / SQL / REST
CS degree valued
Candidate has relevant projects
```

Expected:

```text
fit_score: 75-89
```

### Example B — Strong stack but 2+ mandatory YOE

```text
2+ years backend experience required
Python / TypeScript / SQL
Strong candidate project overlap
Employer says "apply even if you miss requirements"
```

Expected:

```text
fit_score: 25-39
```

### Example C — 1-2 YOE + good stack

```text
1-2 years professional experience required
Python / SQL
Candidate has projects but 0 professional YOE
```

Expected:

```text
fit_score: 40-59
```

### Example D — No YOE stated, customer-facing role

```text
No professional YOE requirement
Python / TypeScript / APIs
Customer-facing responsibilities
```

Do not infer hidden seniority.

Expected when technical fit is good:

```text
fit_score: 60-89
```

depending on remaining gaps.

### Example E — Explicit senior role

```text
Senior Software Engineer
Strong technical stack overlap
```

Expected:

```text
fit_score: 0-39
```

according to the rest of the posting.

---

## 14. Policy Principle

The practical question is:

> **How well does this candidate satisfy this posting?**

That determines score. Never distort the score out of fear of hiding a job. Low-scoring jobs remain saved in `jobs.json` for manual review.

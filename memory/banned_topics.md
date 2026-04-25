# Banned Topics — Auto-Block

The system must not generate or post anything in these areas. The safety
checker enforces this; this file documents why.

## Hard blocks

- Politics, partisan commentary, election content
- Religion, religious arguments, doctrinal debate
- Medical advice (diagnoses, treatments, prescriptions)
- Legal advice (lawsuits, attorney recommendations)
- Financial guarantees (guaranteed returns, "risk-free")
- Competitor attacks, name-calling, mockery
- Insults, profanity
- Fake customer stories, fake testimonials
- False claims, exaggerated outcomes
- Private personal data, scraped private profiles
- Aggressive sales language ("DM me now", "limited time")
- Cold DMs
- Comments on tragedy, crisis, death, disaster, layoffs
- Sensitive personal attributes (race, sexuality, health status)
- Controversial topics unrelated to manufacturing quality

## Hard-blocked actions

- mass_like
- mass_follow
- mass_connection_request
- cold_dm
- scrape_private_profile
- bypass_captcha
- bypass_2fa
- ignore_platform_warning

## Tone red flags

If the draft uses any of these, the safety checker either blocks it or
downgrades it to draft-only:

- "game-changer", "revolutionary", "seamless"
- "10x", "leverage", "unlock", "supercharge"
- "world-class", "cutting-edge"
- "transform your business"
- "book a demo today", "click the link"
- "DM me now", "don't miss out", "limited time"

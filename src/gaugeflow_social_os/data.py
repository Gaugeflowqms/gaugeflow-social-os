from gaugeflow_social_os.models import Initiative, RitualSlot, SignalEvent, TeamMember


TEAM_MEMBERS = [
    TeamMember("M-01", "Ari", "CTO", 12),
    TeamMember("M-02", "Noa", "Product", 10),
    TeamMember("M-03", "Jules", "Design", 8),
    TeamMember("M-04", "Rene", "Growth", 10),
]


INITIATIVES = [
    Initiative("GF-17-01", "Trust graph schema and API", "M-01", 5, 9, 8, 7, []),
    Initiative("GF-17-02", "Creator onboarding funnel", "M-02", 5, 8, 9, 8, []),
    Initiative("GF-17-03", "Social dashboard v1", "M-03", 8, 9, 7, 6, ["GF-17-01"]),
    Initiative("GF-17-04", "Referral growth loops", "M-04", 8, 8, 8, 7, ["GF-17-02"]),
    Initiative("GF-17-05", "Community moderation protocol", "M-02", 3, 7, 8, 9, ["GF-17-01"]),
    Initiative("GF-17-06", "Ops health instrumentation", "M-01", 5, 7, 7, 8, []),
]


SIGNALS = [
    SignalEvent("S-01", "M-01", "burnout_risk", 4, "High context switching and incident load."),
    SignalEvent("S-02", "M-02", "delivery_confidence", 8, "Weekly milestones landed consistently."),
    SignalEvent("S-03", "M-03", "collaboration_friction", 3, "Unclear handoff boundaries with engineering."),
    SignalEvent("S-04", "M-04", "momentum", 7, "Strong response to recent growth experiments."),
]


RITUAL_SLOTS = [
    RitualSlot("R-01", "Monday planning", 8),
    RitualSlot("R-02", "Midweek execution sync", 12),
    RitualSlot("R-03", "Friday ship review", 10),
]

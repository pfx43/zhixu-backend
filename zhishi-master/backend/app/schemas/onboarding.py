from enum import Enum


class OnboardingChannelCode(str, Enum):
    FRIEND = "friend"
    SOCIAL_MEDIA = "social_media"
    SEARCH_ENGINE = "search_engine"
    SCHOOL_TEACHER = "school_teacher"
    COMPETITION_PROJECT = "competition_project"
    OTHER = "other"


class OnboardingIdentityCode(str, Enum):
    STUDENT = "student"
    PROFESSIONAL = "professional"
    RESEARCHER = "researcher"
    TEACHER = "teacher"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class OnboardingUsePurpose(str, Enum):
    LEARNING = "learning"
    RESEARCH = "research"
    WORK = "work"
    COMPETITION = "competition"
    KNOWLEDGE_MANAGEMENT = "knowledge_management"
    OTHER = "other"


class OnboardingFunctionPreference(str, Enum):
    TINA = "tina"
    KNOWLEDGE_BASE = "knowledge_base"
    GRAPH = "graph"
    PRACTICE = "practice"
    ANALYTICS = "analytics"
    OTHER = "other"


class OnboardingDailyUsage(str, Enum):
    LESS_THAN_15_MINUTES = "less_than_15_minutes"
    BETWEEN_15_AND_30_MINUTES = "15_30_minutes"
    BETWEEN_30_AND_60_MINUTES = "30_60_minutes"
    MORE_THAN_60_MINUTES = "more_than_60_minutes"
    UNSURE = "unsure"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"

from prometheus_client import Counter, Histogram

LLM_DURATION = Histogram(
    "jd_explorer_llm_api_duration_seconds",
    "Anthropic API call duration in seconds",
    ["model", "endpoint"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

LLM_TOKENS_INPUT = Counter(
    "jd_explorer_llm_tokens_input_total",
    "Input tokens sent to Anthropic",
    ["model", "endpoint"],
)

LLM_TOKENS_OUTPUT = Counter(
    "jd_explorer_llm_tokens_output_total",
    "Output tokens received from Anthropic",
    ["model", "endpoint"],
)

LLM_ERRORS = Counter(
    "jd_explorer_llm_errors_total",
    "Anthropic API call errors",
    ["endpoint", "error_type"],
)

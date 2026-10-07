"""
Prometheus metrics registry.

Business metrics are defined here as module-level singletons.
Each subsystem increments/observes its own metrics; this module
only declares them so there is a single source of truth.

HTTP metrics (request count, latency, in-flight) are provided
automatically by PrometheusMiddleware (see main.py).

Usage:
    from app.core.metrics import rule_executions
    rule_executions.labels(status="success").inc()
"""

from prometheus_client import Counter, Gauge

# ------------------------------------------------------------------
# Rules Engine
# ------------------------------------------------------------------

rule_executions = Counter(
    "nocode_rule_executions_total",
    "Total rule executions",
    ["status"],  # success | failed | skipped | timeout
)

# ------------------------------------------------------------------
# Workflow Engine
# ------------------------------------------------------------------

workflow_transitions = Counter(
    "nocode_workflow_transitions_total",
    "Total workflow state transitions",
    ["workflow_id", "from_state", "to_state"],
)

workflow_instances_active = Gauge(
    "nocode_workflow_instances_active",
    "Number of non-terminal workflow instances",
)

sla_breaches = Counter(
    "nocode_sla_breaches_total",
    "Total SLA breaches detected by the timer task",
    ["workflow_id"],
)

# ------------------------------------------------------------------
# Data layer
# ------------------------------------------------------------------

record_operations = Counter(
    "nocode_record_operations_total",
    "Record CRUD operations",
    ["operation"],  # create | read | update | delete | list
)

file_uploads = Counter(
    "nocode_file_uploads_total",
    "File upload attempts",
    ["status"],  # success | virus_detected | error
)

# ------------------------------------------------------------------
# Integration / Webhooks
# ------------------------------------------------------------------

webhook_deliveries = Counter(
    "nocode_webhook_deliveries_total",
    "Webhook delivery attempts",
    ["status"],  # delivered | failed | exhausted
)

outbox_events_processed = Counter(
    "nocode_outbox_events_processed_total",
    "Outbox events consumed by the poller",
)

# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------

auth_attempts = Counter(
    "nocode_auth_attempts_total",
    "Authentication attempts",
    ["result"],  # success | wrong_password | totp_required | totp_invalid | inactive
)

token_refreshes = Counter(
    "nocode_token_refreshes_total",
    "JWT refresh operations",
    ["result"],  # success | expired | revoked
)

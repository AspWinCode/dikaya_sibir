"""WorkflowService._dispatch_side_effects (pure function, no DB):

Verifies that notifications/webhooks computed by FSM actions actually get
queued as celery tasks instead of being silently dropped — this was the
bug found while auditing sandbox worker isolation: on_enter/on_exit/
transition actions collected `notify`/`call_webhook` payloads that were
returned in the API response but never dispatched anywhere.
"""

import uuid
from unittest.mock import patch

from app.models.workflow import WorkflowInstance
from app.services.workflow import WorkflowService


def _instance() -> WorkflowInstance:
    return WorkflowInstance(
        id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        app_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        record_id=uuid.uuid4(),
        current_state="draft",
    )


class TestDispatchSideEffects:
    def test_empty_lists_dispatch_nothing(self) -> None:
        with (
            patch("app.worker.tasks.notifications.send_email.apply_async") as email_mock,
            patch("app.worker.tasks.notifications.deliver_rule_webhook.apply_async") as hook_mock,
        ):
            WorkflowService._dispatch_side_effects(_instance(), [], [])
        email_mock.assert_not_called()
        hook_mock.assert_not_called()

    def test_notification_with_recipient_is_queued(self) -> None:
        with patch("app.worker.tasks.notifications.send_email.apply_async") as email_mock:
            WorkflowService._dispatch_side_effects(
                _instance(),
                [
                    {
                        "to": "user@example.com",
                        "subject": "Hi",
                        "template": "Hello {{name}}",
                        "context": {"name": "A"},
                    }
                ],
                [],
            )
        email_mock.assert_called_once()
        kwargs = email_mock.call_args.kwargs["kwargs"]
        assert kwargs["to"] == "user@example.com"
        assert "A" in kwargs["body_html"]
        assert email_mock.call_args.kwargs["queue"] == "notifications"

    def test_notification_without_recipient_is_skipped(self) -> None:
        with patch("app.worker.tasks.notifications.send_email.apply_async") as email_mock:
            WorkflowService._dispatch_side_effects(_instance(), [{"to": None, "subject": "x"}], [])
        email_mock.assert_not_called()

    def test_webhook_is_queued_with_instance_ids(self) -> None:
        instance = _instance()
        with patch("app.worker.tasks.notifications.deliver_rule_webhook.apply_async") as hook_mock:
            WorkflowService._dispatch_side_effects(
                instance,
                [],
                [{"url": "https://hooks.example.com/x", "method": "POST", "payload": {"a": 1}}],
            )
        hook_mock.assert_called_once()
        kwargs = hook_mock.call_args.kwargs["kwargs"]
        assert kwargs["url"] == "https://hooks.example.com/x"
        assert kwargs["app_id"] == str(instance.app_id)
        assert kwargs["entity_id"] == str(instance.entity_id)
        assert kwargs["record_id"] == str(instance.record_id)
        assert hook_mock.call_args.kwargs["queue"] == "notifications"

    def test_webhook_without_url_is_skipped(self) -> None:
        with patch("app.worker.tasks.notifications.deliver_rule_webhook.apply_async") as hook_mock:
            WorkflowService._dispatch_side_effects(
                _instance(), [], [{"method": "POST", "payload": {}}]
            )
        hook_mock.assert_not_called()

    def test_multiple_webhooks_all_queued(self) -> None:
        webhooks = [
            {"url": "https://a.example.com/1", "method": "POST", "payload": {}},
            {"url": "https://b.example.com/2", "method": "GET", "payload": {}},
        ]
        with patch("app.worker.tasks.notifications.deliver_rule_webhook.apply_async") as hook_mock:
            WorkflowService._dispatch_side_effects(_instance(), [], webhooks)
        assert hook_mock.call_count == 2

# Import all models so Alembic autogenerate can discover them
from app.models.identity import RefreshToken, Role, User, UserRole  # noqa: F401
from app.models.catalog import App, AppInviteLink, AppMember, AppModule, Module, ModuleDependency, ModuleVersion  # noqa: F401
from app.models.metamodel import Entity, Field, FieldType, Relation, RelationType  # noqa: F401
from app.models.data import Record, RecordFile  # noqa: F401
from app.models.logic import Rule, RuleExecutionLog, RuleConflictLog, RuleWebhookDelivery  # noqa: F401
from app.models.workflow import (  # noqa: F401
    StateDef, TransitionDef, TransitionLog, WorkflowDef, WorkflowInstance,
)
from app.models.ui import Page, View, ViewFieldConfig  # noqa: F401
from app.models.integration import Outbox, WebhookDelivery, WebhookSubscription  # noqa: F401
from app.models.security import FieldPermission  # noqa: F401

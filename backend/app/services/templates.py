import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.modules import ModuleService

logger = structlog.get_logger(__name__)


TEMPLATES: dict[str, dict[str, Any]] = {
    "trading_company": {
        "name": "Trading company",
        "description": "Enterprise, warehouse, orders, finance and analytics.",
        "modules": ["enterprise", "warehouse", "orders", "finance", "analytics"],
    },
    "manufacturing_company": {
        "name": "Manufacturing company",
        "description": "Enterprise, warehouse, production, finance and analytics.",
        "modules": ["enterprise", "warehouse", "production", "finance", "analytics"],
    },
    "service_company": {
        "name": "Service company",
        "description": "Enterprise, tasks/projects, contracts, finance and IT support.",
        "modules": ["enterprise", "projects", "contracts", "finance", "it_support"],
    },
    "hr_department": {
        "name": "HR department",
        "description": "Enterprise, HR and tasks/projects.",
        "modules": ["enterprise", "hr", "projects"],
    },
    "document_flow": {
        "name": "Document flow",
        "description": "Enterprise, document flow and contracts.",
        "modules": ["enterprise", "documents", "contracts"],
    },
    "financial_accounting": {
        "name": "Financial accounting",
        "description": "Enterprise, finance and analytics.",
        "modules": ["enterprise", "finance", "analytics"],
    },
    "empty": {
        "name": "Empty application",
        "description": "No modules. Configure everything manually.",
        "modules": [],
    },
    # Backward-compatible aliases used by the older frontend gallery.
    "tasks": {
        "name": "Task dispatcher",
        "description": "Projects and tasks.",
        "modules": ["projects"],
    },
    "inventory": {
        "name": "Inventory",
        "description": "Warehouse module.",
        "modules": ["warehouse"],
    },
    "visitors": {
        "name": "Visitor registration",
        "description": "Enterprise base module.",
        "modules": ["enterprise"],
    },
    "survey": {
        "name": "Simple survey",
        "description": "Empty application template.",
        "modules": [],
    },
}


class TemplateNotFoundError(Exception):
    pass


class TemplateService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def list_template_ids(self) -> list[str]:
        return list(TEMPLATES.keys())

    def get_template_meta(self, template_id: str) -> dict[str, Any]:
        template = self._get(template_id)
        return {
            "id": template_id,
            "name": template["name"],
            "description": template["description"],
            "modules": template["modules"],
        }

    async def install(
        self,
        app_id: uuid.UUID,
        template_id: str,
        actor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        template = self._get(template_id)
        module_service = ModuleService(self._db)

        modules_installed: list[str] = []
        entities_created = 0
        fields_created = 0
        pages_created = 0

        for module_code in template["modules"]:
            result = await module_service.install_module(
                app_id=app_id,
                module_code=module_code,
                actor_id=actor_id or uuid.UUID(int=0),
            )
            modules_installed.append(result.module.code)
            modules_installed.extend(result.installed_dependencies)
            entities_created += result.entities_created
            fields_created += result.fields_created
            pages_created += result.pages_created

        logger.info(
            "template_installed",
            app_id=str(app_id),
            template_id=template_id,
            modules=sorted(set(modules_installed)),
        )
        return {
            "modules_installed": sorted(set(modules_installed)),
            "entities_created": entities_created,
            "fields_created": fields_created,
            "pages_created": pages_created,
        }

    def _get(self, template_id: str) -> dict[str, Any]:
        if template_id not in TEMPLATES:
            raise TemplateNotFoundError(template_id)
        return TEMPLATES[template_id]

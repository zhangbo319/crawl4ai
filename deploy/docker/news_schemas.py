from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SiteConfigPayload(BaseModel):
    site_code: str
    site_name: str
    base_url: str
    entry_url: str
    rule_json: Dict[str, Any]
    default_config_json: Dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class SchedulePayload(BaseModel):
    site_id: int
    cron_expr: str
    timezone: str = "Asia/Shanghai"
    is_enabled: bool = True


class SitesResponse(BaseModel):
    items: List[Dict[str, Any]]


class SchedulesResponse(BaseModel):
    items: List[Dict[str, Any]]


class JobLogsResponse(BaseModel):
    items: List[Dict[str, Any]]


class SiteRunPayload(BaseModel):
    limit: int = Field(default=100, ge=1, le=200)
    target_date: str = ""
    force_refresh: bool = False
    save_raw: bool = False
    archive: bool = True
    trigger_type: str = "manual"
    schedule_id: Optional[int] = None


class ScheduleUpdatePayload(BaseModel):
    cron_expr: str
    timezone: str = "Asia/Shanghai"
    is_enabled: bool = True

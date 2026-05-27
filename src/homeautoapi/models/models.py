from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field


class HomeAssistantHeaders(BaseModel):
    model_config = ConfigDict(extra="forbid")

    Authorization: str


class HomeAssistantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    effect: str | None = None
    rgb_color: list[int] | None = None
    brightness: int | None = None
    brightness_pct: int | None = None
    transition: float | None = None
    flash: Literal["short", "long"] | None = None
    temperature: float | None = None
    hvac_mode: str | None = None
    preset_mode: str | None = None
    fan_mode: str | None = None
    swing_mode: str | None = None

class HomeAssistantAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal['GET', 'POST']
    endpoint: str
    headers: HomeAssistantHeaders
    body: HomeAssistantBody

class RagResponseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[HomeAssistantAction]
    chat_response: str

class HALightDeviceAttributesSchema(BaseModel):
    brightness: int | None = None
    color_mode: str | None = None
    effect: str | None = None
    effect_list: list[str] | None = None
    friendly_name: str | None = None
    supported_features: int | None = None
    hs_color: list[int] | None = None
    rgb_color: list[int] | None = None
    supported_color_modes: list[str] | None = None
    xy_color: list[float] | None = None



class HAEntityContextSchema(BaseModel):
    id: str
    parent_id: str | None = None
    user_id: str | None = None

class HAEntityStateSchema(BaseModel):
    attributes: dict
    entity_id: str
    last_changed: str
    last_updated: str
    last_reported: str | None = None
    state: str
    context: HAEntityContextSchema | None = None

class LightDeviceSchema(BaseModel):
    attributes: HALightDeviceAttributesSchema
    entity_id: str
    last_changed: str
    last_updated: str
    state: str

class SetLightStateParametersSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    state: Literal["on", "off"]
    color: list[int] | None = None
    brightness: int | None = None
    effect: str | None = None
    reverse: bool | None = None
    intensity: int | None = None
    speed: int | None = None


class ActivateSceneParametersSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str


class SetLightStateActionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: Literal["set_light_state"]
    parameters: SetLightStateParametersSchema


class ActivateSceneActionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: Literal["activate_scene"]
    parameters: ActivateSceneParametersSchema

class AgentResponseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[SetLightStateActionSchema | ActivateSceneActionSchema]
    chat_response: str


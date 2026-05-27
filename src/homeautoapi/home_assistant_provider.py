import asyncio
import os
from typing import Literal
import httpx, websockets, json
from homeautoapi.models.models import RagResponseSchema, LightDeviceSchema, HAEntityStateSchema
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.sql import text



HOME_ASSISTANT_TOKEN = os.environ.get("HA_TOKEN", "")
HOME_ASSISTANT_BASE_URL = os.environ.get("HA_BASE_URL", "http://192.168.0.50:8123")
POSTGRES_URL = os.environ.get("POSTGRES_URL", "postgresql://postgres:password@localhost:5432/homeautoapi")

class HomeAssistantProvider:
    def __init__(self, api_url: str, api_token: str):
        self.api_url = api_url
        self.api_token = api_token

    @staticmethod
    async def execute(request: RagResponseSchema, base_url: str) -> None:
        """Execute the generated REST calls against the HA instance."""
        async with httpx.AsyncClient() as client:
            for action in request.actions:
                headers = {"Authorization": action.headers.Authorization.replace("Bearer <HA_TOKEN>", f"Bearer {HOME_ASSISTANT_TOKEN}")}
                body = action.body.model_dump(exclude_none=True)

                print(f"Executing {action.method} {action.endpoint} with body {body} ...")

                response = await client.request(action.method, f"{base_url}{action.endpoint}", headers=headers, json=body)
                response.raise_for_status()

    async def get_light_devices(self) -> list[dict]:
        """Example method to fetch light entities from Home Assistant."""
        url = f"{self.api_url}/api/states"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
        response.raise_for_status()
        if response.status_code == 200:
            return [entity for entity in response.json() if entity["entity_id"].startswith("light.")]
        return []
    
    async def get_scenes(self) -> list[dict]:
        """Example method to fetch scenes from Home Assistant."""
        url = f"{self.api_url}/api/states"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
        response.raise_for_status()
        if response.status_code == 200:
            return [entity for entity in response.json() if entity["entity_id"].startswith("scene.")]
        return []
    
    async def get_number_entities(self) -> list[dict]:
        """Example method to fetch number entities from Home Assistant."""
        url = f"{self.api_url}/api/states"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
        response.raise_for_status()
        if response.status_code == 200:
            return [entity for entity in response.json() if entity["entity_id"].startswith("number.")]
        return []

    async def get_switch_entities(self) -> list[dict]:
        """Example method to fetch switch entities from Home Assistant."""
        url = f"{self.api_url}/api/states"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
        response.raise_for_status()
        if response.status_code == 200:
            return [entity for entity in response.json() if entity["entity_id"].startswith("switch.")]
        return []
    
    async def _get_device_internal_ids(self) -> list[tuple[str, str]]:
        """Fetch the internal IDs for all entities in Home Assistant, this is required to set attributes on entities that don't have native support for those attributes in HA e.g. effect speed and intensity."""
        async with websockets.connect(f"ws://{self.api_url}:8123/api/websocket") as ws:
            await ws.recv()
            await ws.send(json.dumps({"type": "auth", "access_token": self.api_token}))
            await ws.recv()

            await ws.send(json.dumps({"id": 1, "type": "config/entity_registry/list"}))
            entities = json.loads(await ws.recv())["result"]

            return [(e["entity_id"], e["device_id"]) for e in entities]
    
    async def set_light_state(self, 
                              entity_id: str, 
                              state: Literal["on", "off"],
                              color: tuple[int, int, int] | None = None,
                              brightness: int | None = None, 
                              effect: str | None = None,
                              reverse: Literal["on", "off"] | None = None,
                              intensity: int | None = None,
                              speed: int | None = None) -> None:
        """Example method to set the state of a light entity."""
        if not entity_id.startswith("light."):
            return
        url = f"{self.api_url}/api/services/light/turn_{state}"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        body: dict[str, object] = {"entity_id": entity_id}

        if color:
            body["rgb_color"] = color
        if brightness:
            body["brightness"] = brightness
        if effect:
            body["effect"] = effect
        if reverse == "on":
            await self.set_attribute_state("switch." + entity_id.split(".")[1] + "_reverse", "on")
        if intensity:
            await self.set_attribute_state("number." + entity_id.split(".")[1] + "_intensity", str(intensity))
        if speed:
            await self.set_attribute_state("number." + entity_id.split(".")[1] + "_speed", str(speed))

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()

    async def activate_scene(self, entity_id: str) -> None:
        """Example method to activate a scene."""
        if not entity_id.startswith("scene."):
            return
        url = f"{self.api_url}/api/services/scene/turn_on"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        body = {"entity_id": entity_id}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
    
    async def set_attribute_state(self, entity_id: str, value: str) -> None:
        """Method to set an arbitrary attribute of an entity. Specifically for handling speed and intensity for effects that don't have native support in HA."""
        url = f"{self.api_url}/api/services/number/set_value"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        body = {"entity_id": entity_id, 
                "value": value}
        # print(f"Setting attribute {entity_id} to value {value} ...")

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
    
    async def refresh_device_registry(self) -> None:
        """Method to trigger a refresh of the HA device registry, this will populate the devices and relationships in the registry database"""

        lights = await self.get_light_devices()
        scenes = await self.get_scenes()
        numbers = await self.get_number_entities()
        switches = await self.get_switch_entities()
        entity_device_pairs = await self._get_device_internal_ids()

        print(f"Fetched {len(lights)} lights, {len(scenes)} scenes, {len(numbers)} number entities, and {len(switches)} switch entities from Home Assistant")

        pg_engine = create_async_engine(POSTGRES_URL, echo=False)
        async with AsyncSession(pg_engine) as session:
            query = """
                    DROP TABLE IF EXISTS light_devices;
                    CREATE TABLE IF NOT EXISTS light_devices (
                        id SERIAL PRIMARY KEY,
                        state VARCHAR(50) NOT NULL,
                        entity_id VARCHAR(255) UNIQUE NOT NULL,
                        friendly_name VARCHAR(255) NOT NULL,
                    );
                    DROP TABLE IF EXISTS light_effects;
                    CREATE TABLE IF NOT EXISTS light_effects (
                        id SERIAL PRIMARY KEY,
                        effect_name VARCHAR(255) NOT NULL,
                        );

                    DROP TABLE IF EXISTS light_effect_bridge;
                    CREATE TABLE IF NOT EXISTS light_effect_bridge (
                        effect_id INT NOT NULL REFERENCES light_effects(id),
                        entity_id VARCHAR(255) NOT NULL,
                    );
                    DROP TABLE IF EXISTS scenes;
                    CREATE TABLE IF NOT EXISTS scenes (
                        id SERIAL PRIMARY KEY,
                        state VARCHAR(50) NOT NULL,
                        entity_id VARCHAR(255) UNIQUE NOT NULL,
                        friendly_name VARCHAR(255) NOT NULL,
                    );
                    DROP TABLE IF EXISTS number_entities;
                    CREATE TABLE IF NOT EXISTS number_entities (
                        id SERIAL PRIMARY KEY,
                        state VARCHAR(50) NOT NULL,
                        entity_id VARCHAR(255) UNIQUE NOT NULL,
                        friendly_name VARCHAR(255) NOT NULL,
                    );

                    DROP TABLE IF EXISTS switch_entities;
                    CREATE TABLE IF NOT EXISTS switch_entities (
                        id SERIAL PRIMARY KEY,
                        state VARCHAR(50) NOT NULL,
                        entity_id VARCHAR(255) UNIQUE NOT NULL,
                        friendly_name VARCHAR(255) NOT NULL,
                    );
                    DROP TABLE IF EXISTS device_registry;
                    CREATE TABLE IF NOT EXISTS device_registry (
                        entity_id VARCHAR(255) PRIMARY KEY,
                        device_id VARCHAR(255) UNIQUE NOT NULL,
                    );"""
            session.add(session.execute(statement=text(query)))
            for light in lights:
                session.add(session.execute(
                    text("INSERT INTO light_devices (state, entity_id, friendly_name) VALUES (:state, :entity_id, :friendly_name) ON CONFLICT (entity_id) DO UPDATE SET state = EXCLUDED.state, friendly_name = EXCLUDED.friendly_name"),
                    {"state": light.get("state"), "entity_id": light["entity_id"], "friendly_name": light.get("attributes", {}).get("friendly_name", "")}
                ))
                for effect in light.get("attributes", {}).get("effect_list", []):
                    session.add(session.execute(
                        text("INSERT INTO light_effects (effect_name) VALUES (:effect_name) ON CONFLICT (effect_name) DO NOTHING"),
                        {"effect_name": effect}
                    ))

                    session.add(session.execute(text("""INSERT INTO light_effect_bridge (effect_id, entity_id) VALUES ((SELECT id FROM light_effects WHERE effect_name = :effect_name), :entity_id)"""), {"effect_name": effect, "entity_id": light["entity_id"]}))
            
            for scene in scenes:
                session.add(session.execute(
                    text("INSERT INTO scenes (state, entity_id, friendly_name) VALUES (:state, :entity_id, :friendly_name) ON CONFLICT (entity_id) DO UPDATE SET state = EXCLUDED.state, friendly_name = EXCLUDED.friendly_name"),
                    {"state": scene.get("state"), "entity_id": scene["entity_id"], "friendly_name": scene.get("attributes", {}).get("friendly_name", "")}
                ))

            for number in numbers:
                session.add(session.execute(
                    text("INSERT INTO number_entities (state, entity_id, friendly_name) VALUES (:state, :entity_id, :friendly_name) ON CONFLICT (entity_id) DO UPDATE SET state = EXCLUDED.state, friendly_name = EXCLUDED.friendly_name"),
                    {"state": number.get("state"), "entity_id": number["entity_id"], "friendly_name": number.get("attributes", {}).get("friendly_name", "")}
                ))
            
            for switch in switches:
                session.add(session.execute(
                    text("INSERT INTO switch_entities (state, entity_id, friendly_name) VALUES (:state, :entity_id, :friendly_name) ON CONFLICT (entity_id) DO UPDATE SET state = EXCLUDED.state, friendly_name = EXCLUDED.friendly_name"),
                    {"state": switch.get("state"), "entity_id": switch["entity_id"], "friendly_name": switch.get("attributes", {}).get("friendly_name", "")}
                ))
            
            for pair in entity_device_pairs:
                session.add(session.execute(
                    text("INSERT INTO device_registry (entity_id, device_id) VALUES (:entity_id, :device_id) ON CONFLICT (entity_id) DO UPDATE SET device_id = EXCLUDED.device_id"),
                    {"entity_id": pair[0], "device_id": pair[1]}
                ))
            await session.commit()




if __name__ == "__main__":
    ha_provider = HomeAssistantProvider(HOME_ASSISTANT_BASE_URL, HOME_ASSISTANT_TOKEN)
    asyncio.run(ha_provider.refresh_device_registry())
    # print(lights[0].model_dump_json(indent=4))
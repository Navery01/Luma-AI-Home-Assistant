import asyncio, json
import os
from pprint import pprint
import numpy as np
from openai import OpenAI
from homeautoapi.home_assistant_provider import HomeAssistantProvider
from homeautoapi.rag_dispatcher import RAGDispatcher
from homeautoapi.models.models import AgentResponseSchema

CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-4o-mini")
API_KEY = os.environ.get("OPENAI_API_KEY")

TOOL_SCHEMA = [{
    "name": "set_light_state",
    "description": "Set the state of a light device, including brightness, on/ off, color, and effects.",
    "parameters": {
            "entity_id": {"type": "string", "description": "The entity_id of the light device to control."},
            "state": {"type": "string", "literal": ["on", "off"], "description": "This controls whether the light is turned on or off."},
            "color": {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3, "description": "The RGB color values to set, if applicable."},
            "brightness": {"type": "integer", "description": "The brightness level to set (0-255)."},
            "effect": {"type": "string", "description": "The lighting effect to apply, if any."},
            "reverse": {"type": "boolean", "description": "Whether to reverse the effect."},
            "intensity": {"type": "integer", "description": "The intensity level."},
            "speed": {"type": "integer", "description": "The speed of the effect."}
        },
        "required": ["entity_id", "state"]
    
},
 {
    "name": "activate_scene",
    "description": "Activate a Home Assistant premade scene.",
    "parameters": {
            "entity_id": {"type": "string", "description": "The entity_id of the scene to activate."}
        },
        "required": ["entity_id"]
    
}]
SYSTEM_PROMPT = f"""
    You are a Home Assistant automation assistant.
    You will be given a subset of devices from a Home Assistant device registry (JSON) and a user instruction.
    Your job is to produce a structured JSON response that lists the exact tools needed to carry out
    the instruction as specified in the tool schema.
    Rules:
    - Use only the devices provided in the context. Do not invent entity_ids.
    - Use only listed effects in the device.attributes.effect_list. 
    - If the user requests an effect not in the list, choose the closest one and manually set colors to match the requested effect.    
    - Use the provided tool schema to execute actions via the API. Do not deviate from the schema.
    - Only use the provided tools, do not attempt to execute API calls directly or use any tools/parameters not listed in the schema.
    - Only use the "activate_scene" tool for activating premade scenes, and only with the "entity_id" parameter.
    - The "activate_scene" tool should only be used for premade scenes that the user explicitly instructs to activate, do not use it for scenes that can be executed by setting light states.
    - The top-level JSON tag for the list of API calls must be "actions", and each call must include "method", "endpoint", "headers", and "body" fields.
    - Populate the "chat_response" field in the output JSON with a natural-language response to the user that confirms the action taken, use non-confirming language e.g. "Ok on it".
    - At least one color value must be at the maximum value (255) to ensure the light turns on, if the user requests a color change when turning on a light, set the brightness to 255 if not specified by the user.
    - When using the "set_light_state" tool, use maximum brightness (255) unless otherwise specified by the user
    - The chat response should be in written as Wheatly from Portal 2 would say it. Specifically, it should be very casual and conversational, and include some light humor.
    - In the chat response DO NOT mention the device registry or the API call details. The user doesn't need to know about those, and it will just confuse them. Just confirm the action you're taking in response to their instruction, in a casual and conversational way.
    - In the chat response DO NOT confirm that the actions were sucessfully executed. Just confirm that you're taking the action
    """.strip()


class AgentDispatcher:
    def __init__(self):
        self.client = OpenAI(api_key=API_KEY)
        self.home_assistant_provider = HomeAssistantProvider(
            os.environ.get("HA_BASE_URL", "http://192.168.0.50:8123"), 
            os.environ.get("HA_TOKEN", ""))
        self.rag_dispatcher = RAGDispatcher()

    async def dispatch(self, user_message: str) -> str:

        json_context = await self.home_assistant_provider.get_light_devices() # + await self.home_assistant_provider.get_scenes()
        top_entities = self.rag_dispatcher.get_relevant_devices(user_message, json_context, top_k=15)

        user_message = (
            f"User instruction: {user_message}"
            f"\n\nDevice registry (only use these devices to fulfill the instruction):\n{top_entities}"
        )

        response = await asyncio.to_thread(
            lambda: self.client.chat.completions.parse(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                response_format=AgentResponseSchema
            )
        )

        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("Model returned no parsed response content.")
        else:
            print(f"LLM response: {parsed.actions},\n chat_response: {parsed.chat_response}")   
            for action in parsed.actions:
                if action.tool_name == "set_light_state":
                    tool_parameters = action.parameters.model_dump(exclude_none=True)
                    asyncio.create_task(self.home_assistant_provider.set_light_state(**tool_parameters))
                    print(f"Executed set_light_state with parameters: {tool_parameters}")
                elif action.tool_name == "activate_scene":
                    tool_parameters = {"entity_id": action.parameters.entity_id}
                    asyncio.create_task(self.home_assistant_provider.activate_scene(**tool_parameters))
                    print(f"Executed activate_scene with parameters: {tool_parameters}")


            return parsed.chat_response
    



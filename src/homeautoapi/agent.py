import litellm, json
from homeautoapi.ha_mcp_client import HAMCPClient
from homeautoapi.db_helper import ClientFact
from pprint import pprint

class Agent:
    """
    A model agnostic agent that can use any LLM supported by LiteLLM and can be extended to use any tool.
    LiteLLM reads these standard env var names automatically:
    ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, GROQ_API_KEY
    """
    
    def __init__(self, 
                 name: str="Luma", 
                 model:str= "anthropic/claude-sonnet-4-6" #openai/gpt-4o"
                 ):
        self.name = name
        self.model = model
    
        
        
       

    async def run_agent(self,
                        user_message:str,
                        tools:list[dict], 
                        mcp_client:HAMCPClient,
                        client_facts:list[ClientFact] = [],
                        chat_history:list = [], 
                        model:str | None = None) -> str:
        """Run the Home Assistant agent with the given user message, tools, and MCP client."""
        model = model or self.model
        print(f"Running agent with model {model}")
        INITIAL_SYSTEM_PROMPT = f"""
            You are {self.name}, the AI personality for this home. You have direct access to Home Assistant
            and can control lights, climate, media players, and more. Be helpful, warm, and concise.
            When you need to act on the home, use the available tools ensure you are familiar with the device states before taking any action.
            Do not make up device names or actions. Do not include emojis in your responses. 
            """.strip() + ("\n\n" + "\n".join([f"Session Fact: {fact.fact}" for fact in client_facts]) if client_facts else "")
        
    # TODO: Chat history should be injected as user/assistant alternating pairs.
        messages = [
            {"role": "system", "content": [{"type": "text", "text": INITIAL_SYSTEM_PROMPT, "cache_control":{"type":"ephemeral"}}]},
            {"role": "user",   "content": user_message},
            {"role": "system", "content": [{"type": "text", "text": "Previous Chat: " + entry} for entry in chat_history]}
        ]

        while True:
            response = await litellm.acompletion(
                model = model,
                messages = messages,
                tools = tools,
                tool_choice = "auto",
                max_tokens = 1000,
                timeout = 40
            )

            msg: dict = response.choices[0].message # type: ignore
            messages.append(msg)

            if not msg.get("tool_calls"):
                return msg.get("content", "")
            
            for tool_call in msg.get("tool_calls", []):
                tool_name = tool_call.get("function", {}).get("name")
                tool_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))

                result = await mcp_client.call_tool(tool_name, tool_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id":tool_call.get("id"),
                    "name": tool_name,
                    "content": json.dumps(result)
                })
            print(f"{'='*20} Agent Messages {'='*20}")
            pprint(msg.get("content", ""))

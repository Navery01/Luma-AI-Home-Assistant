import json, logging
from homeautoapi.home_assistant_conversation_client import HomeAssistantConversationClient, RouteResult
from homeautoapi.database_provider import ClientFact
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools


class Agent:
    """
    A model agnostic agent that can use any LLM supported by LiteLLM and can be extended to use any tool.
    LiteLLM reads these standard env var names automatically:
    ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, GROQ_API_KEY
    """
    
    def __init__(self, 
                 name: str="Luma", 
                 model:str= "claude-sonnet-4-6" #openai/gpt-4o"
                 ):
        self.name = name
        self.model = model
        self.mcp_client = MultiServerMCPClient(
            HomeAssistantConversationClient().config # type: ignore
        )
    
    async def run_agent(self,
                        user_message:str,
                        client_facts:list[ClientFact] = [],
                        chat_history:list = []):
        """Run the Home Assistant agent with the given user message, tools, and MCP client."""

        route = await HomeAssistantConversationClient().route_intent(user_message)
        if route.result == RouteResult.SUCCESS:
            return

        model = self.model
        logging.info(f"Running agent with model {model}")
        INITIAL_SYSTEM_PROMPT = f"""
            You are {self.name}, the AI personality for this home. You have direct access to Home Assistant
            and can control lights, climate, media players, and more. When you need to act on the home, 
            use the available tools ensure you are familiar with the device states before taking any action.
            Do not make up device names or actions. Do not include conversation messages if the response also contains actions.
            """.strip() + ("\n\n" + "\n".join([f"Session Fact: {fact.fact}" for fact in client_facts]) if client_facts else "")

        messages = {"messages": [
            {"role": "system", "content": INITIAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
            ]}

        tools = await self.mcp_client.get_tools()
        
        agent = create_agent(
            model=model,
            tools=tools
        )
        response = await agent.ainvoke(messages, print_mode="updates") # type: ignore

        return response

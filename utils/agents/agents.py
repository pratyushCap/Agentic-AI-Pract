# agents/base_agent.py
import inspect
import json
import re
from typing import Any, Dict, List, Optional
import csv

from llm.llm_config import llm_client
from utils.logger import setup_logger

logger = setup_logger(__name__)


class BaseAgent:
    """Base agent class for all specialized agents."""

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        tools: Optional[Dict[str, callable]] = None,
    ):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.tools = tools or {}
        self.conversation_history: List[Dict[str, Any]] = []
        self.state: Dict[str, Any] = {}

    def add_tool(self, tool_name: str, tool_func: callable):
        """Register a tool."""
        self.tools[tool_name] = tool_func

    def _build_tool_schema(self) -> List[Dict[str, Any]]:
        """Convert tools to OpenAI-compatible function schemas."""
        schemas: List[Dict[str, Any]] = []
        for tool_name, tool_func in self.tools.items():
            description = inspect.getdoc(tool_func) or f"Tool {tool_name}"
            signature = inspect.signature(tool_func)
            properties: Dict[str, Any] = {}
            required: List[str] = []

            for param_name, param in signature.parameters.items():
                if param_name == "self":
                    continue

                if param.default is inspect.Parameter.empty:
                    required.append(param_name)

                properties[param_name] = {
                    "type": self._map_annotation_to_json_type(param.annotation),
                    "description": f"Parameter {param_name}",
                }

            schema = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
            schemas.append(schema)

        return schemas

    def _map_annotation_to_json_type(self, annotation: Any) -> str:
        """Map Python annotations to JSON Schema simple types."""
        if annotation in (str, "str"):
            return "string"
        if annotation in (int, "int"):
            return "integer"
        if annotation in (float, "float"):
            return "number"
        if annotation in (bool, "bool"):
            return "boolean"
        if getattr(annotation, "__origin__", None) is list:
            return "array"
        return "string"

    def _extract_file_path(self, user_message: str) -> Optional[str]:
        """Extract a likely file path from a user prompt."""
        match = re.search(r"([A-Za-z]:\\[^\s]+|[^\s]+\.(csv|json))", user_message)
        if match:
            return match.group(1)
        return None

    def _classify_intent(self, user_message: str) -> str:
        """Classify a prompt into a supported tool intent."""
        text = user_message.lower()

        if re.search(r"\b(load|open|read)\b", text) and re.search(r"\.(csv|json)\b", text):
            return "load_data"
        if re.search(r"\b(summarize|summary|describe|stats|statistics|preview)\b", text):
            return "summarize"
        if re.search(r"\b(correlation|correlate|relationship)\b", text):
            return "correlation"
        if re.search(r"\b(outlier|outliers|anomaly|anomalies)\b", text):
            return "outliers"
        if re.search(r"\b(schema|table|columns|database)\b", text):
            return "schema"
        if re.search(r"\b(sql|query|select|from)\b", text):
            return "sql"
        return "chat"

    def _try_local_tool_plan(self, user_message: str) -> Optional[Any]:
        """Run a simple local tool plan when tool-calling is unsupported by the model."""
        intent = self._classify_intent(user_message)
        text = user_message.lower()

        if intent == "load_data":
            file_path = self._extract_file_path(user_message)
            if file_path and "load_data" in self.tools:
                result = self.tools["load_data"](file_path)
                self.state["loaded_data"] = result
                self.state["loaded_path"] = file_path

                try:
                    if file_path.endswith(".csv"):
                        with open(file_path, newline="", encoding="utf-8") as f:
                            reader = csv.DictReader(f)
                            self.state["dataframe"] = [row for row in reader]
                    elif file_path.endswith(".json"):
                        with open(file_path, encoding="utf-8") as f:
                            self.state["dataframe"] = json.load(f)
                    else:
                        self.state["dataframe"] = None
                except FileNotFoundError:
                    self.state["dataframe"] = None

                return result

        if intent == "summarize" and "dataframe" in self.state and self.state["dataframe"] is not None:
            if "get_summary_statistics" in self.tools:
                result = self.tools["get_summary_statistics"](self.state["dataframe"])
                self.state["last_summary"] = result
                return result

        if intent == "correlation" and "dataframe" in self.state and self.state["dataframe"] is not None:
            if "get_correlation_matrix" in self.tools:
                result = self.tools["get_correlation_matrix"](self.state["dataframe"])
                self.state["last_correlation"] = result
                return result

        if intent == "outliers" and "dataframe" in self.state and self.state["dataframe"] is not None:
            if "find_outliers" in self.tools:
                column = ""
                for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", user_message):
                    if token.lower() not in {"find", "outlier", "outliers", "in", "the", "a", "an"}:
                        column = token
                        break

                default_column = None
                if isinstance(self.state["dataframe"], list) and self.state["dataframe"]:
                    default_column = list(self.state["dataframe"][0].keys())[0]
                result = self.tools["find_outliers"](
                    self.state["dataframe"], column or default_column
                )
                self.state["last_outliers"] = result
                return result

        if intent == "schema" and "get_table_schema" in self.tools:
            table_name = re.search(r"table\s+([A-Za-z0-9_\.]+)", user_message, re.IGNORECASE)
            if table_name:
                result = self.tools["get_table_schema"](table_name.group(1), "")
                self.state["last_schema"] = result
                return result

        if intent == "sql" and "execute_query" in self.tools:
            query = re.search(r"(?:select|with|insert|update|delete)[\s\S]+", user_message, re.IGNORECASE)
            if query:
                result = self.tools["execute_query"](query.group(0), "")
                self.state["last_sql"] = result
                return result

        return None

    def run(
        self,
        user_message: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Any:
        """Send a user message to the configured LLM and return its response."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]
        tools = self._build_tool_schema()

        local_result = self._try_local_tool_plan(user_message)
        if local_result is not None:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Use the tool result below to answer the user's request in a concise way.\n"
                        f"Tool result: {json.dumps(local_result)}"
                    ),
                }
            )
            try:
                return llm_client.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=None,
                )
            except Exception:
                return local_result

        response = llm_client.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools if tools else None,
        )

        if isinstance(response, dict) and response.get("type") == "tool_call":
            for tool_call in response.get("tool_calls", []):
                function_name = getattr(tool_call.function, "name", None)
                arguments = getattr(tool_call.function, "arguments", "{}")
                try:
                    args = json.loads(arguments)
                except json.JSONDecodeError:
                    args = {}

                if function_name in self.tools:
                    tool_result = self.tools[function_name](**args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": function_name,
                            "content": json.dumps(tool_result),
                        }
                    )

            follow_up = llm_client.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=None,
            )
            return follow_up

        return response

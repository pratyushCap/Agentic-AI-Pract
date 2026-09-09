from typing import List, Union
from pathlib import Path

from tools.sql_tools import DataEngineeringTools
from utils.agents.agents import BaseAgent


class DataEngineeringAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="data_engineering",
            description="Prepares financial and business data for analysis, executes queries, and builds datasets for modeling.",
            system_prompt=(
                "You are a data engineering assistant. "
                "Prepare and validate data, run queries, and build repeatable data workflows."
            ),
            tools={
                "execute_query": DataEngineeringTools.execute_query,
                "load_data_source": DataEngineeringTools.load_data_source,
                "get_table_schema": DataEngineeringTools.get_table_schema,
            },
        )

    def build_dataset(self, source: Union[str, List[str]], connection_string: str = "") -> dict:
        """Create a standardized dataset from one or more files, a folder, or a query."""
        if isinstance(source, list) or (
            isinstance(source, str)
            and (source.lower().endswith(('.csv', '.json')) or Path(source).is_dir())
        ):
            result = self.tools["load_data_source"](source)
        else:
            result = self.tools["execute_query"](source, connection_string)

        return {
            "status": result.get("status"),
            "rows": result.get("rows"),
            "columns": result.get("columns"),
            "preview": result.get("data"),
            "records": result.get("records"),
            "file_count": result.get("file_count", 0),
        }
